const express = require("express");
const mongoose = require("mongoose");
const cors = require("cors");
require("dotenv").config();
const protect = require('./middleware/authMiddleware');

const app = express();

// Middleware
app.use(cors());
app.use(express.json({ limit: '10mb' }));

// MongoDB Connection
mongoose.connect(process.env.MONGO_URI, {
  useNewUrlParser: true,
  useUnifiedTopology: true
})
.then(() => console.log("✅ Connected to MongoDB"))
.catch((err) => console.error("❌ MongoDB connection error:", err));

// Routes (to be created later)
const userRoutes = require("./routes/userRoutes");
const sessionRoutes = require("./routes/sessionRoutes");
const chatRoutes = require('./controllers/chatController');
app.use("/api/users", userRoutes);
app.use("/api/sessions", sessionRoutes);
app.use('/api/chat',protect,chatRoutes); 

// Start Server
const PORT = process.env.PORT || 8080;
app.listen(PORT, () => {
  console.log(`🚀 Server running on port ${PORT}`);
});
