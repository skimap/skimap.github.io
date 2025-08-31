import json
import os
import shutil
import numpy as np
import gpxpy
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from scipy.spatial import distance

# Convert track points to a feature vector
def track_to_features(points, ref_tracks):
    """
    Converts a GPX track to a feature vector based on its similarity to reference tracks.

    Args:
        points (np.ndarray): Array of points [(lat, lon), ...].
        ref_tracks (list): List of reference tracks [(name, points)].

    Returns:
        np.ndarray: Feature vector representing distances to reference tracks.
    """
    features = []
    for _, ref_points in ref_tracks:
        ref_points = np.array(ref_points)
        distances = distance.cdist(points, ref_points)
        avg_distance = np.mean(np.min(distances, axis=0))
        features.append(avg_distance)
    return np.array(features)

# Load reference tracks as training data
def load_reference_tracks(ref_file):
    """
    Loads reference tracks from a JSON file.

    Args:
        ref_file (str): Path to the JSON file containing reference tracks.

    Returns:
        list: List of tuples (name, points) for each reference track.
    """
    with open(ref_file, encoding="utf-8") as f:
        ref_points = json.load(f)

    ref_tracks = []
    for ski_area in ref_points["items"]:
        for track in ski_area["tracks"]:
            points = [(p["lat"], p["lon"]) for p in track["points"]]
            ref_tracks.append((f"{ski_area['name']} - {track['trackname']}", points))
    return ref_tracks

# Prepare data
def prepare_training_data(ref_tracks):
    X = []
    y = []
    track_lengths = {}  # To store track lengths for weight calculation

    for label, ref_points in ref_tracks:
        features = track_to_features(np.array(ref_points), ref_tracks)
        X.append(features)
        y.append(label)
        
        # Calculate total length of the track (sum of distances between consecutive points)
        track_length = np.sum([distance.euclidean(ref_points[i], ref_points[i+1]) for i in range(len(ref_points) - 1)])
        track_lengths[label] = track_lengths.get(label, 0) + track_length  # Aggregate length for each track class

    X = np.array(X)
    y = np.array(y)

    return X, y, track_lengths

# Calculate class weights based on track length
def calculate_class_weights(track_lengths):
    total_length = sum(track_lengths.values())
    class_weights = {label: length / total_length for label, length in track_lengths.items()}
    return class_weights

# Train a classifier with class weights
def train_classifier(X_train, y_train, class_weights):
    clf = RandomForestClassifier(n_estimators=100, random_state=42, class_weight=class_weights)
    clf.fit(X_train, y_train)
    return clf

# Function to classify and save a GPX file into a subfolder based on its predicted class
# Function to classify and save a GPX file into a subfolder based on its predicted class
def classify_and_save_track(gpx_points, ref_tracks, clf, filename, base_directory="test_identified"):
    """
    Classifies a GPX track and saves it into a subfolder based on its predicted class.

    Args:
        gpx_points (np.ndarray): Array of GPX points [(lat, lon), ...].
        ref_tracks (list): List of reference tracks [(name, points)].
        clf (sklearn model): Trained classification model.
        filename (str): Name of the GPX file.
        base_directory (str): Base directory to save identified tracks.
    """
    # Predict the class of the track using clf.predict (using the correct method)
    features = track_to_features(gpx_points, ref_tracks)
    predicted_label = clf.predict([features])[0]
    
    # Create a subfolder for the predicted class
    class_folder = os.path.join(base_directory, predicted_label)
    os.makedirs(class_folder, exist_ok=True)
    
    # Move the file to the class folder
    source_path = os.path.join(track_directory, filename)
    destination_path = os.path.join(class_folder, filename)
    shutil.move(source_path, destination_path)
    print(f"{filename}: Moved to {destination_path}")


# Directories
track_directory = "tracks/identification/"

# Load reference tracks
ref_tracks = load_reference_tracks("json/slopes/interpolated_ref_points.json")

# Prepare training data and calculate class weights
X, y, track_lengths = prepare_training_data(ref_tracks)
class_weights = calculate_class_weights(track_lengths)

# Train-Test Split
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Train a Random Forest Classifier with class weights
clf = train_classifier(X_train, y_train, class_weights)

# Evaluate the model
y_pred = clf.predict(X_test)
print(f"Model Accuracy: {accuracy_score(y_test, y_pred) * 100:.2f}%")

# Iterate through GPX files and classify them
for filename in os.listdir(track_directory):
    if filename.endswith(".gpx"):
        with open(os.path.join(track_directory, filename), "r") as gpx_file:
            gpx = gpxpy.parse(gpx_file)

        for gpx_track in gpx.tracks:
            for gpx_segment in gpx_track.segments:
                gpx_points = np.array([(p.latitude, p.longitude) for p in gpx_segment.points])
                classify_and_save_track(gpx_points, ref_tracks, clf, filename)
