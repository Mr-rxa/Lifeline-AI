from flask import Flask, request, jsonify, send_from_directory
import csv, time, os

app = Flask(__name__)
CSV_FILE = 'live_positions.csv'

# Create CSV file with header if missing
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'lat', 'lon', 'speed_kmph', 'ts'])

def update_csv(aid, lat, lon, speed, ts):
    rows = []
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

    # Remove old entry for this ambulance
    rows = [r for r in rows if r['id'] != aid]
    rows.append({
        'id': aid,
        'lat': str(lat),
        'lon': str(lon),
        'speed_kmph': str(speed),
        'ts': str(ts)
    })

    with open(CSV_FILE, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['id', 'lat', 'lon', 'speed_kmph', 'ts'])
        writer.writeheader()
        writer.writerows(rows)

@app.route('/update_location', methods=['POST'])
def update_location():
    data = request.get_json(force=True)
    aid = data.get('id', 'AMB')
    lat = float(data['lat'])
    lon = float(data['lon'])
    speed = data.get('speed_kmph', '')
    ts = time.time()

    update_csv(aid, lat, lon, speed, ts)
    return jsonify({'status': 'ok', 'ts': ts})

@app.route('/positions', methods=['GET'])
def positions():
    rows = []
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    return jsonify(rows)

# Serve GPS sender page directly
@app.route('/')
def serve_gps_sender():
    return """
    <!DOCTYPE html>
    <html>
    <head>
      <title>Ambulance GPS Sender</title>
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <style>
        body { font-family: Arial, sans-serif; padding: 20px; max-width: 600px; margin: 0 auto; }
        #status { color: green; margin-top: 10px; }
        #error { color: red; margin-top: 10px; }
        #coords { font-weight: bold; margin-top: 10px; background: #f0f0f0; padding: 10px; border-radius: 5px; }
        input { padding: 8px; font-size: 16px; border: 2px solid #ddd; border-radius: 4px; }
        .url-display { background: #e8f5e9; padding: 10px; margin: 10px 0; border-radius: 5px; word-break: break-all; }
      </style>
    </head>
    <body>
      <h2>🚑 GPS Sender</h2>
      <div class="url-display">
        <strong>Server URL:</strong> <span id="currentUrl"></span>
      </div>
      <p>Sending live GPS location to the tracker server...</p>

      <label for="ambId">Ambulance ID: </label>
      <input type="text" id="ambId" value="AMB1" style="padding: 5px; margin-bottom: 10px;">

      <div id="coords">Waiting for GPS...</div>
      <div id="status"></div>
      <div id="error"></div>

      <script>
        const NGROK_URL = window.location.origin;
        document.getElementById("currentUrl").innerText = NGROK_URL;

        function getAmbulanceId() {
          return document.getElementById("ambId").value || "AMB1";
        }

        function sendLocation(lat, lon, speed) {
          const AMBULANCE_ID = getAmbulanceId();
          const payload = { id: AMBULANCE_ID, lat: lat, lon: lon, speed_kmph: speed || 0 };

          fetch(NGROK_URL + "/update_location", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          })
          .then(res => res.json())
          .then(data => {
            document.getElementById("status").innerText = "✅ Sent at " + new Date().toLocaleTimeString();
            console.log("Server response:", data);
          })
          .catch(err => {
            document.getElementById("error").innerText = "❌ Send error: " + err;
          });
        }

        function success(pos) {
          const lat = pos.coords.latitude;
          const lon = pos.coords.longitude;
          const speed = pos.coords.speed ? (pos.coords.speed * 3.6).toFixed(1) : 0;

          document.getElementById("coords").innerText = `📍 Lat: ${lat}, Lon: ${lon}, Speed: ${speed} km/h`;
          sendLocation(lat, lon, speed);
        }

        function error(err) {
          document.getElementById("error").innerText = "⚠ GPS error: " + err.message;
          console.warn("GPS error:", err);

          // fallback to Delhi
          const fallbackLat = 28.6139;
          const fallbackLon = 77.2090;
          sendLocation(fallbackLat, fallbackLon, 0);
        }

        if ("geolocation" in navigator) {
          navigator.geolocation.watchPosition(success, error, {
            enableHighAccuracy: true,
            maximumAge: 0
          });
        } else {
          document.getElementById("error").innerText = "❌ Geolocation not supported in this browser.";
        }
      </script>
    </body>
    </html>
    """

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
