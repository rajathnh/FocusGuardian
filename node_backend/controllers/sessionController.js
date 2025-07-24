const Groq = require('groq-sdk'); // 1. Import Groq SDK
const Session = require('../models/Session');
const User = require('../models/User');
const asyncHandler = require('express-async-handler'); // Or use try/catch
const mongoose = require('mongoose'); // <-- ADD THIS LINE

// 2. Initialize Groq Client (Ensure GROQ_API_KEY is in .env)
// You might initialize this once outside the functions if preferred
const groq = new Groq({
    apiKey: process.env.GROQ_API_KEY,
});

const ANALYSIS_INTERVAL_SECONDS = 3; // How often frontend sends data (used for calculating time deltas)
const MIN_SECONDS_BETWEEN_CALLS = 0; 
const MIN_MS_BETWEEN_CALLS = MIN_SECONDS_BETWEEN_CALLS * 1000;
// @desc    Start a new session
// @route   POST /api/sessions/start
// @access  Private
exports.startSession = async (req, res) => {
    try {
        const userId = req.user.id; // From authMiddleware

        // Check if user already has an active session (optional, prevents duplicates)
        const existingActiveSession = await Session.findOne({ userId, endTime: null });
        if (existingActiveSession) {
            return res.status(400).json({ message: 'Active session already exists', sessionId: existingActiveSession._id });
        }

        const newSession = new Session({
            userId,
            startTime: new Date(),
            // Initialize other fields if needed
        });

        await newSession.save();

        res.status(201).json({ message: 'Session started', sessionId: newSession._id });
    } catch (error) {
        console.error("Error starting session:", error);
        res.status(500).json({ message: 'Server error starting session' });
    }
};


// @desc    Receive ONE combined data URI (from frontend canvas), analyze with Groq
// @route   POST /api/sessions/data/:sessionId
// @access  Private
exports.processSessionData = async (req, res) => {
    const { sessionId } = req.params;
    const userId = req.user.id;

    // 1. Validate the incoming JSON data from Python
    const { focus, appName, activity } = req.body;
    if (typeof focus !== 'boolean' || !appName || !activity) {
        return res.status(400).json({ message: 'Invalid analysis data payload. Required fields: focus, appName, activity.' });
    }

    try {
        // 2. Find the Active Session (this logic is still needed)
        const session = await Session.findOne({ _id: sessionId, userId: userId, endTime: null });
        if (!session) {
            // This is an important signal to the Python script to stop.
            return res.status(404).json({ message: 'Active session not found. Please stop monitoring.' });
        }

        // 3. Update the Database using the received data
        const ANALYSIS_INTERVAL_SECONDS = 5; // Or your Python script's interval
        const timeIncrement = ANALYSIS_INTERVAL_SECONDS;

        const sanitizedAppName = appName.replace(/\./g, '_').replace(/^\$/, '_$');
        const user = await User.findById(userId);
        if (!user) {
            return res.status(404).json({ message: 'User associated with session not found.' });
        }

        if (focus) {
            session.focusTime += timeIncrement;
            user.totalFocusTime += timeIncrement;
        } else {
            session.distractionTime += timeIncrement;
            user.totalDistractionTime += timeIncrement;
        }

        const sessionAppTime = session.appUsage.get(sanitizedAppName) || 0;
        session.appUsage.set(sanitizedAppName, sessionAppTime + timeIncrement);
        session.markModified('appUsage');

        const userAppTime = user.appUsage.get(sanitizedAppName) || 0;
        user.appUsage.set(sanitizedAppName, userAppTime + timeIncrement);
        user.markModified('appUsage');
        
        await Promise.all([session.save(), user.save()]);
        
        console.log(`[Session ${sessionId}] DB Updated via Python: focus=${focus}, app=${sanitizedAppName}`);

        res.status(200).json({ message: 'Data point processed successfully.' });

    } catch (error) {
        console.error(`Error processing local data for session ${sessionId}:`, error);
        res.status(500).json({ message: 'Internal server error while processing data.' });
    }
};
exports.stopSession = async (req, res) => {
    const { id: sessionId } = req.params; // Changed param name for clarity
    const userId = req.user.id;

    try {
        const session = await Session.findOneAndUpdate(
            { _id: sessionId, userId, endTime: null }, // Find active session for this user
            { $set: { endTime: new Date() } }, // Set the end time
            { new: true } // Return the updated document
        );

        if (!session) {
            return res.status(404).json({ message: 'Active session not found or already stopped' });
        }

        // Optional: Perform final calculations or summarization here if needed

        res.status(200).json({ message: 'Session stopped successfully', session });
    } catch (error) {
        console.error("Error stopping session:", error);
        res.status(500).json({ message: 'Server error stopping session' });
    }
};

// controllers/analysisController.js

exports.getDailyAppUsage = asyncHandler(async (req, res) => {
    // 1. Get User ID and Number of Days from Request
    console.log("Hello")
    const userId = new mongoose.Types.ObjectId(req.user.id); // From protect middleware
    const numberOfDays = parseInt(req.query.days, 10) || 7; // Default to last 7 days

    // Input validation
    if (numberOfDays <= 0 || numberOfDays > 90) { // Add a reasonable limit
        return res.status(400).json({ message: 'Invalid number of days requested.' });
    }

    // 2. Calculate Date Range
    const endDate = new Date(); // Up to the current moment
    const startDate = new Date();
    startDate.setHours(0, 0, 0, 0); // Start of today
    startDate.setDate(startDate.getDate() - (numberOfDays - 1)); // Go back N-1 days to get N full days

    console.log(`Fetching daily app usage for user ${userId} from ${startDate.toISOString()} to ${endDate.toISOString()} (${numberOfDays} days).`);

    try {
        // 3. Define the Aggregation Pipeline
        const appUsagePipeline = [
            // Stage 1: Match sessions for the user within the date range
            {
                $match: {
                    userId: userId,
                    // Consider sessions that *started* within the range
                    startTime: { $gte: startDate },
                    // Ensure appUsage exists and is not empty (optional optimization)
                    // appUsage: { $exists: true, $ne: {} }
                }
            },
            // Stage 2: Convert the appUsage map to an array of key-value pairs
            {
                $project: {
                    // Keep other fields if needed for debugging, otherwise just project appUsage
                    _id: 0, // Exclude session ID unless needed later
                    appUsageArray: { $objectToArray: "$appUsage" }
                }
            },
            // Stage 3: Unwind the array to process each app entry individually
            {
                $unwind: "$appUsageArray" // Creates a doc per app entry per session
            },
            // Stage 4: Group by the app name (key 'k') and sum the time (value 'v')
            {
                $group: {
                    _id: "$appUsageArray.k", // Group by app name (key from the array)
                    totalTime: { $sum: "$appUsageArray.v" } // Sum the time spent (value)
                }
            },
            // Stage 5: Project to rename fields for better output format
            {
                $project: {
                    _id: 0, // Remove the default _id field
                    appName: "$_id", // Rename grouping key to appName
                    totalTime: 1 // Keep the calculated totalTime (in seconds)
                }
            },
            // Stage 6: Sort by total time descending (optional, but useful)
            {
                $sort: {
                    totalTime: -1
                }
            }
        ];

        // 4. Execute the Aggregation
        const dailyAppStats = await Session.aggregate(appUsagePipeline);

        // 5. Send the results
        res.status(200).json(dailyAppStats); // Sends an array: [{ appName: 'App1', totalTime: 1850 }, ...]

    } catch (error) {
        console.error("Error fetching daily app usage statistics:", error);
        res.status(500).json({ message: 'Server error fetching daily app usage data' });
    }
});

// @desc    Get aggregated daily session stats for the user
// @route   GET /api/analysis/daily
// @access  Private
exports.getDailyAnalysis = asyncHandler(async (req, res) => {
    console.log("Req recieved")

    const userId = new mongoose.Types.ObjectId(req.user.id); // Ensure it's ObjectId
    const numberOfDays = parseInt(req.query.days, 10) || 7; // Default to last 7 days

    if (numberOfDays <= 0 || numberOfDays > 90) { // Add a reasonable limit
        return res.status(400).json({ message: 'Invalid number of days requested.' });
    }

    // Calculate the start date for the query
    const startDate = new Date();
    startDate.setHours(0, 0, 0, 0); // Start of today
    startDate.setDate(startDate.getDate() - (numberOfDays - 1)); // Go back N-1 days

    console.log(`Fetching daily analysis for user ${userId} from ${startDate.toISOString()} for ${numberOfDays} days.`);

    try {
        const dailyStats = await Session.aggregate([
            // 1. Match relevant sessions for the user within the date range
            {
                $match: {
                    userId: userId,
                    startTime: { $gte: startDate } // Only sessions started on or after startDate
                    // Optionally add: endTime: { $ne: null } if you only want completed sessions included
                }
            },
            // 2. Group by Date (extracting the date part from startTime)
            {
                $group: {
                    _id: {
                        // Group by year, month, day of the startTime
                        $dateToString: { format: "%Y-%m-%d", date: "$startTime", timezone: "UTC" } // Use user's timezone if possible/needed
                    },
                    totalFocusTime: { $sum: "$focusTime" },
                    totalDistractionTime: { $sum: "$distractionTime" },
                    // More complex: Aggregate appUsage (summing time per app per day)
                    // This requires unwinding and regrouping, potentially slower.
                    // Let's skip daily app aggregation for simplicity first.
                    // We can add it later if needed.
                    sessionCount: { $sum: 1 } // Count sessions per day
                }
            },
            // 3. Project to reshape the output
            {
                $project: {
                    _id: 0, // Remove the default _id
                    date: "$_id", // Rename _id to date
                    focusTime: "$totalFocusTime",
                    distractionTime: "$totalDistractionTime",
                    sessionCount: "$sessionCount",
                    // Calculate focus percentage for the day
                    focusPercentage: {
                       $cond: {
                            if: { $gt: [{ $add: ["$totalFocusTime", "$totalDistractionTime"] }, 0] },
                            then: {
                                $round: [
                                    {
                                        $multiply: [
                                            { $divide: ["$totalFocusTime", { $add: ["$totalFocusTime", "$totalDistractionTime"] }] },
                                            100
                                        ]
                                    },
                                    0 // Round to 0 decimal places
                                ]
                            },
                            else: 0 // Avoid division by zero
                       }
                    }
                }
            },
            // 4. Sort by date ascending
            {
                $sort: { date: 1 }
            }
        ]);

        // Optional: Fill in missing dates with zero values if needed for charts
        const filledStats = fillMissingDates(startDate, numberOfDays, dailyStats);

        res.status(200).json(filledStats);

    } catch (error) {
        console.error("Error fetching daily analysis:", error);
        res.status(500).json({ message: 'Server error fetching daily analysis' });
    }
});

// Helper function to fill missing dates (can be moved to utils)
function fillMissingDates(startDate, numberOfDays, stats) {
    const resultsMap = new Map(stats.map(s => [s.date, s]));
    const filled = [];
    const currentDate = new Date(startDate); // Start from the calculated start date

    for (let i = 0; i < numberOfDays; i++) {
        const dateStr = currentDate.toISOString().split('T')[0]; // Format as YYYY-MM-DD

        if (resultsMap.has(dateStr)) {
            filled.push(resultsMap.get(dateStr));
        } else {
            // Add an entry with zero values for missing days
            filled.push({
                date: dateStr,
                focusTime: 0,
                distractionTime: 0,
                sessionCount: 0,
                focusPercentage: 0
            });
        }
        currentDate.setDate(currentDate.getDate() + 1); // Move to the next day
    }
    return filled;
}
// --- Add other necessary controllers ---

// @desc    Get current active session for logged-in user
// @route   GET /api/sessions/current
// @access  Private
exports.getCurrentSession = async (req, res) => {
     try {
        const session = await Session.findOne({ userId: req.user.id, endTime: null });
         if (!session) {
             return res.status(404).json({ message: 'No active session found' });
         }
        res.status(200).json(session);
     } catch (error) {
         console.error("Error fetching current session:", error);
         res.status(500).json({ message: 'Server error' });
     }
 };

// @desc    Get all sessions for logged-in user (for dashboard history)
// @route   GET /api/sessions/history
// @access  Private
exports.getSessionById = asyncHandler(async (req, res) => {
    console.log("Req 1 recieved")
    const sessionId = req.params.id;
    const userId = req.user.id; // From protect middleware

    // Validate Session ID format (basic check)
    if (!mongoose.Types.ObjectId.isValid(sessionId)) {
        return res.status(400).json({ message: 'Invalid session ID format' });
    }

    // Find the session and ensure it belongs to the logged-in user
    const session = await Session.findOne({ _id: sessionId, userId: userId });

    if (!session) {
        // Use 404 Not Found if the session doesn't exist or doesn't belong to the user
        return res.status(404).json({ message: 'Session not found or access denied' });
    }

    // Return the full session details
    res.status(200).json(session);
});
exports.getSessionHistory = async (req, res) => {
    console.log("Req recieved")

    try {
        const sessions = await Session.find({ userId: req.user.id })
                                       .sort({ startTime: -1 }); // Sort newest first
        res.status(200).json(sessions);
    } catch (error) {
        console.error("Error fetching session history:", error);
        res.status(500).json({ message: 'Server error' });
    }
};


// @desc    Get overall user stats (can also be part of getUserProfile)
// @route   GET /api/sessions/stats
// @access  Private
// Note: You might already have this in userController/getUserProfile.
// If so, you don't need a separate route here. Just showing data access.
exports.getUserStats = async (req, res) => {
     try {
         // We get the user object from the authMiddleware
         const user = await User.findById(req.user.id).select('totalFocusTime totalDistractionTime appUsage');
         if (!user) {
            return res.status(404).json({ message: 'User not found' });
        }
         // Convert Map to a plain object for JSON response if needed by frontend library
         const appUsageObject = Object.fromEntries(user.appUsage);

        res.status(200).json({
            totalFocusTime: user.totalFocusTime,
            totalDistractionTime: user.totalDistractionTime,
            appUsage: appUsageObject,
        });
    } catch (error) {
        console.error("Error fetching user stats:", error);
        res.status(500).json({ message: 'Server error' });
    }
};


// (Ensure sessionRoutes.js uses these controller functions)