import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
import joblib
import os
import sys

# --- Add the parent directory to the Python path ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

# --- Import your own helper files and constants ---
from helpers.config import COL_PLANT_NAME

# --- Configuration ---
MODELS_DIR = 'models'
DATA_DIR = 'data'
LABELED_DATA_FILE = 'labeled_health_data.csv' # The name of your new labeled file

# --- Define what we want to predict and what features to use ---
TARGET_VARIABLE = 'Health_Status' # Our new target
FEATURES = ['Temperature_C', 'Humidity', 'Dendrometer (microns)', 'Plant Name']

def train_classifier_model():
    """Loads labeled data, trains a classifier, and saves it."""
    
    print("--- Starting Health Classification Model Training ---")
    
    # --- 1. Load Labeled Data ---
    data_path = os.path.join(DATA_DIR, LABELED_DATA_FILE)
    if not os.path.exists(data_path):
        print(f"Error: Labeled data file not found at '{data_path}'.")
        print("Please create and label your data first.")
        return

    df = pd.read_csv(data_path)
    print(f"Labeled data loaded successfully. Found {len(df)} total rows.")

    # --- 2. Prepare Data for Modeling ---
    df.dropna(subset=[TARGET_VARIABLE] + FEATURES, inplace=True)
    
    for col in ['Temperature_C', 'Humidity', 'Dendrometer (microns)']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
    df.dropna(subset=['Temperature_C', 'Humidity', 'Dendrometer (microns)'], inplace=True)

    if df.empty:
        print("Error: Data is empty after cleaning. Cannot train model.")
        return

    print(f"Data prepared. Using {len(df)} rows for training.")
    print("\nHealth Status distribution in the data:")
    print(df[TARGET_VARIABLE].value_counts())

    X = df[FEATURES]
    y = df[TARGET_VARIABLE]
    X = pd.get_dummies(X, columns=['Plant Name'], prefix='Plant')
    
    model_columns = X.columns.tolist()
    joblib.dump(model_columns, os.path.join(MODELS_DIR, 'classifier_columns.pkl'))
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    # --- 3. Train the Classifier Model ---
    print("\nTraining RandomForestClassifier...")
    # We use a classifier model for this task
    model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)
    print("Model training complete.")
    
    # --- 4. Evaluate the Model ---
    preds = model.predict(X_test)
    accuracy = accuracy_score(y_test, preds)
    print(f"\nModel Accuracy on test data: {accuracy:.2f}")
    
    print("\nClassification Report:")
    print(classification_report(y_test, preds))

    # --- 5. Save the Trained Model ---
    model_path = os.path.join(MODELS_DIR, 'health_classifier_model.pkl')
    joblib.dump(model, model_path)
    print(f"\nClassifier model and column list saved successfully to '{MODELS_DIR}' directory.")
    print("--- Training Complete ---")

if __name__ == '__main__':
    train_classifier_model()
