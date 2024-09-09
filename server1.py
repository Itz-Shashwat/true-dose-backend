from flask import Flask, request, jsonify
import hashlib
import datetime
import csv
import json
import requests

app = Flask(__name__)

# Function to generate hash for verification (updated to SHA-256)
def generate_hash(data):
    hash_object = hashlib.sha256(data.encode())
    return hash_object.hexdigest()

# Function to check expiry date
def check_expiry(expiry_date_str):
    expiry_date = datetime.datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
    current_date = datetime.date.today()
    return expiry_date > current_date

# Function to check salt composition
def check_salt_composition(expected_composition, actual_composition):
    for salt, expected_value in expected_composition.items():
        if salt not in actual_composition or actual_composition[salt] != expected_value:
            return False
    return True

# Function to load batch data from CSV
def load_batch_data_from_csv():
    batch_data = {}
    try:
        with open('your_batch_data.csv', mode='r') as file:
            csv_reader = csv.DictReader(file)
            for row in csv_reader:
                # Assuming CSV has columns: batch_number, hash, expiry_date, salt_composition, max_transit_temperature
                batch_data[row['batch_number']] = {
                    'hash': row['hash'],
                    'salt_composition': json.loads(row['salt_composition']),  # Ensure valid JSON in the CSV
                    'expiry_date': row['expiry_date'],
                    'max_transit_temperature': float(row['max_transit_temperature'])
                }
    except Exception as e:
        print(f"Error loading CSV: {str(e)}")
    return batch_data

# Function to fetch expected hash from another server
def fetch_expected_hash(batch_number):
    try:
        # Call the hash verification server
        response = requests.post('http://localhost:5001/verify-hash', json={'batch_no': batch_number})
        if response.status_code == 200:
            return response.json().get('hash')
        else:
            return None
    except Exception as e:
        print(f"Error fetching hash: {str(e)}")
        return None

# Endpoint to handle connection requests
@app.route('/connect', methods=['GET'])
def connect():
    return "Connected to Web Application"

# Endpoint to handle barcode data upload and process it
@app.route('/upload-barcode', methods=['POST'])
def upload_barcode():
    batch_data = load_batch_data_from_csv()
    try:
        # Get the JSON data from the request
        data = request.json
        
        # Extract the barcode data, batch number, and other details
        barcode_data = data.get('barcode_data', '')
        actual_salt_composition = data.get('salt_composition', {})
        transit_temperature = data.get('transit_temperature', 0)
        
        if not barcode_data:
            return jsonify({"error": "No barcode data provided"}), 400

        # Assuming barcode_data contains the batch number
        batch_number = barcode_data  # In a real system, parse this from the barcode
        
        # Check if the batch number exists in the batch_data dictionary
        if batch_number in batch_data:
            # Fetch expected hash from the server
            expected_hash = fetch_expected_hash(batch_number)
            if not expected_hash:
                return jsonify({"error": "Batch number not found or hash retrieval failed"}), 404
            
            # Generate a hash locally and compare
            generated_hash = generate_hash(batch_number)
            
            # Step 1: Hash verification
            if expected_hash != generated_hash:
                return jsonify({"error": "Invalid hash, unauthorized batch"}), 403
            
            # Step 2: Salt composition check
            expected_composition = batch_data[batch_number]["salt_composition"]
            if not check_salt_composition(expected_composition, actual_salt_composition):
                return jsonify({"error": "Salt composition mismatch"}), 400
            
            # Step 3: Expiry date check
            expiry_date = batch_data[batch_number]["expiry_date"]
            if not check_expiry(expiry_date):
                return jsonify({"error": "Medicine is expired"}), 400

            # Step 4: Transit condition check (e.g., temperature during transport)
            max_allowed_temp = batch_data[batch_number]["max_transit_temperature"]
            if transit_temperature > max_allowed_temp:
                return jsonify({"error": f"Exceeded max transit temperature ({max_allowed_temp}°C)"}), 400

            # Calculate the quality score
            quality_score = 100  # Start with full score
            days_left = (datetime.datetime.strptime(expiry_date, "%Y-%m-%d").date() - datetime.date.today()).days
            if days_left < 180:  # Near expiry
                quality_score -= 20
            
            if transit_temperature > (max_allowed_temp - 5):  # Near max allowed temp
                quality_score -= 15

            return jsonify({
                "message": "Uploaded successfully",
                "quality_score": quality_score
            }), 200
        
        else:
            return jsonify({"error": "Batch number not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Main function to run the Flask server
if __name__ == '__main__':
    app.run(debug=True)
