# combine_datasets.py
import pandas as pd
import os
import glob

# --- Configuration ---
# The folder where you've placed all the individual CSV files
SOURCE_FOLDER = "team_datasets"

# The name for the final, combined master dataset file
MASTER_FILENAME = "master_productivity_dataset.csv"

def main():
    print(f"--- Combining CSVs from '{SOURCE_FOLDER}' folder ---")

    if not os.path.isdir(SOURCE_FOLDER):
        print(f"Error: Source folder '{SOURCE_FOLDER}' not found.")
        print("Please create it and place your team's CSV files inside.")
        return

    # Find all files ending with .csv in the source folder
    csv_files = glob.glob(os.path.join(SOURCE_FOLDER, "*.csv"))

    if not csv_files:
        print(f"Error: No CSV files found in '{SOURCE_FOLDER}'.")
        return

    print(f"Found {len(csv_files)} files to combine:")
    for f in csv_files:
        print(f"  - {os.path.basename(f)}")

    # Read each CSV into a list of pandas DataFrames
    list_of_dfs = []
    for filename in csv_files:
        try:
            df = pd.read_csv(filename)
            # Ensure the DataFrame has the expected columns before appending
            if 'text' in df.columns and 'label' in df.columns:
                list_of_dfs.append(df)
            else:
                print(f"Warning: Skipping {os.path.basename(filename)} because it's missing 'text' or 'label' columns.")
        except pd.errors.EmptyDataError:
            print(f"Warning: Skipping empty file: {os.path.basename(filename)}")
        except Exception as e:
            print(f"Error reading {os.path.basename(filename)}: {e}")
    
    if not list_of_dfs:
        print("No valid dataframes to combine. Exiting.")
        return

    # Use pandas.concat to stack all the dataframes into one
    master_df = pd.concat(list_of_dfs, ignore_index=True)

    # CRITICAL: Drop any rows that might be completely empty or malformed
    master_df.dropna(subset=['text', 'label'], inplace=True)
    # Ensure label is an integer
    master_df['label'] = master_df['label'].astype(int)

    # Optional but highly recommended: Shuffle the combined data
    # This mixes everyone's data together, which is better for training.
    master_df = master_df.sample(frac=1, random_state=42).reset_index(drop=True)

    # Save the final, combined DataFrame to a new CSV file
    master_df.to_csv(MASTER_FILENAME, index=False)

    print("\n--- Combination Complete! ---")
    print(f"Successfully combined {len(list_of_dfs)} files into '{MASTER_FILENAME}'.")
    print(f"The master dataset contains {len(master_df)} total rows.")

if __name__ == '__main__':
    main()