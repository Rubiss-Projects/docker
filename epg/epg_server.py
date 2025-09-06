#!/usr/bin/env python3
"""
Simple web server to serve EPG data with automatic refresh
"""

from flask import Flask, send_file, jsonify
import os
import threading
import time
import subprocess
import schedule
from datetime import datetime

app = Flask(__name__)

def generate_epg():
    """Generate EPG data using the grabber script"""
    print(f"[{datetime.now()}] Starting EPG generation...")
    try:
        result = subprocess.run(['python', 'epg_grabber.py'], 
                              capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            print(f"[{datetime.now()}] EPG generation completed successfully")
        else:
            print(f"[{datetime.now()}] EPG generation failed: {result.stderr}")
    except subprocess.TimeoutExpired:
        print(f"[{datetime.now()}] EPG generation timed out")
    except Exception as e:
        print(f"[{datetime.now()}] EPG generation error: {e}")

def run_scheduler():
    """Run the background scheduler"""
    # Generate EPG immediately on startup
    generate_epg()
    
    # Schedule EPG refresh every 3 hours
    schedule.every(3).hours.do(generate_epg)
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

@app.route('/guide.xml')
def serve_guide():
    """Serve the EPG guide XML file"""
    if os.path.exists('/app/guide.xml'):
        return send_file('/app/guide.xml', mimetype='text/xml')
    else:
        return "EPG guide not found. Please wait for initial grab to complete.", 404

@app.route('/channels')
def list_channels():
    """List available channels - exact match to HDHomeRun lineup"""
    channels = {
        # Exact match to HDHomeRun lineup from http://192.168.50.130/lineup.json
        "2.1": {"name": "WPBT-HD", "number": "2.1", "network": "PBS", "call_sign": "WPBT-HD"},
        "2.2": {"name": "Create", "number": "2.2", "network": "Create", "call_sign": "Create"},
        "2.3": {"name": "WPBTHC", "number": "2.3", "network": "PBS", "call_sign": "WPBTHC"},
        "2.4": {"name": "Kids", "number": "2.4", "network": "PBS Kids", "call_sign": "Kids"},
        "4.1": {"name": "WFOR-TV", "number": "4.1", "network": "CBS", "call_sign": "WFOR-TV"},
        "4.2": {"name": "WFORTV2", "number": "4.2", "network": "Start TV", "call_sign": "WFORTV2"},
        "4.3": {"name": "WFORTV3", "number": "4.3", "network": "Dabl", "call_sign": "WFORTV3"},
        "4.4": {"name": "WFORTV4", "number": "4.4", "network": "CBSN", "call_sign": "WFORTV4"},
        "4.5": {"name": "WFORTV5", "number": "4.5", "network": "Fave TV", "call_sign": "WFORTV5"},
        "6.1": {"name": "WTVJ", "number": "6.1", "network": "NBC", "call_sign": "WTVJ"},
        "6.2": {"name": "COZI TV", "number": "6.2", "network": "Cozi TV", "call_sign": "COZI TV"},
        "6.3": {"name": "AMCRIME", "number": "6.3", "network": "True Crime", "call_sign": "AMCRIME"},
        "6.4": {"name": "Oxygen", "number": "6.4", "network": "Oxygen", "call_sign": "Oxygen"},
        "7.1": {"name": "WSVN", "number": "7.1", "network": "FOX", "call_sign": "WSVN"},
        "7.2": {"name": "ABC", "number": "7.2", "network": "ABC", "call_sign": "ABC"},
        "7.3": {"name": "The365", "number": "7.3", "network": "The 365", "call_sign": "The365"},
        "7.4": {"name": "DEFY", "number": "7.4", "network": "Defy TV", "call_sign": "DEFY"},
        "13.1": {"name": "WURH", "number": "13.1", "network": "Independent", "call_sign": "WURH"},
        "17.1": {"name": "WLRN-HD", "number": "17.1", "network": "PBS", "call_sign": "WLRN-HD"},
        "18.1": {"name": "ABC18.1", "number": "18.1", "network": "ABC", "call_sign": "ABC18.1"},
        "23.1": {"name": "WLTV-DT", "number": "23.1", "network": "Univision", "call_sign": "WLTV-DT"},
        "23.2": {"name": "JUSTICE", "number": "23.2", "network": "Justice Network", "call_sign": "JUSTICE"},
        "23.3": {"name": "Nosey", "number": "23.3", "network": "Nosey", "call_sign": "Nosey"},
        "23.4": {"name": "MSGold", "number": "23.4", "network": "Movies! Gold", "call_sign": "MSGold"},
        "23.6": {"name": "ShopLC", "number": "23.6", "network": "Shop LC", "call_sign": "ShopLC"},
        "33.1": {"name": "WBFS-TV", "number": "33.1", "network": "CW", "call_sign": "WBFS-TV"},
        "33.2": {"name": "WBFSTV2", "number": "33.2", "network": "Antenna TV", "call_sign": "WBFSTV2"},
        "33.3": {"name": "WBFSTV3", "number": "33.3", "network": "CourtTV", "call_sign": "WBFSTV3"},
        "33.4": {"name": "WBFSTV4", "number": "33.4", "network": "Story Television", "call_sign": "WBFSTV4"},
        "33.5": {"name": "WBFSTV5", "number": "33.5", "network": "True Crime Network", "call_sign": "WBFSTV5"},
        "33.6": {"name": "WBFSTV6", "number": "33.6", "network": "Newsy", "call_sign": "WBFSTV6"},
        "33.7": {"name": "WBFSTV7", "number": "33.7", "network": "Rewind TV", "call_sign": "WBFSTV7"},
        "39.1": {"name": "WSFL-DT", "number": "39.1", "network": "CW", "call_sign": "WSFL-DT"},
        "39.2": {"name": "CourtTV", "number": "39.2", "network": "CourtTV", "call_sign": "CourtTV"},
        "39.3": {"name": "AntTV", "number": "39.3", "network": "Antenna TV", "call_sign": "AntTV"},
        "39.4": {"name": "IONPLUS", "number": "39.4", "network": "ION Plus", "call_sign": "IONPLUS"},
        "39.5": {"name": "QVC", "number": "39.5", "network": "QVC", "call_sign": "QVC"},
        "42.1": {"name": "WXEL-HD", "number": "42.1", "network": "PBS", "call_sign": "WXEL-HD"},
        "45.1": {"name": "TBN HD", "number": "45.1", "network": "TBN", "call_sign": "TBN HD"},
        "45.2": {"name": "Merit", "number": "45.2", "network": "Merit Street", "call_sign": "Merit"},
        "45.3": {"name": "Inspire", "number": "45.3", "network": "Inspire", "call_sign": "Inspire"},
        "45.4": {"name": "ONTV4U", "number": "45.4", "network": "ONTV4U", "call_sign": "ONTV4U"},
        "45.5": {"name": "POSITIV", "number": "45.5", "network": "Positiv", "call_sign": "POSITIV"},
        "51.1": {"name": "WSCV", "number": "51.1", "network": "Telemundo", "call_sign": "WSCV"},
        "51.2": {"name": "EXITOS", "number": "51.2", "network": "Exitos", "call_sign": "EXITOS"},
        "51.4": {"name": "WSCV-PB", "number": "51.4", "network": "NBC Universo", "call_sign": "WSCV-PB"},
        "63.1": {"name": "WBEC-HD", "number": "63.1", "network": "Independent", "call_sign": "WBEC-HD"},
        "63.2": {"name": "WBEC-SD", "number": "63.2", "network": "Independent", "call_sign": "WBEC-SD"},
        "67.1": {"name": "ION", "number": "67.1", "network": "ION", "call_sign": "ION"},
        "67.2": {"name": "Mystery", "number": "67.2", "network": "ION Mystery", "call_sign": "Mystery"},
        "67.3": {"name": "DEFY", "number": "67.3", "network": "Defy TV", "call_sign": "DEFY"},
        "67.4": {"name": "DABL", "number": "67.4", "network": "Dabl", "call_sign": "DABL"},
        "67.5": {"name": "BUSTED", "number": "67.5", "network": "TruTV", "call_sign": "BUSTED"},
        "67.6": {"name": "GameSho", "number": "67.6", "network": "Game Show Network", "call_sign": "GameSho"},
        "67.7": {"name": "HSN2", "number": "67.7", "network": "HSN2", "call_sign": "HSN2"},
        "67.8": {"name": "HSN", "number": "67.8", "network": "HSN", "call_sign": "HSN"},
        "67.9": {"name": "QVC", "number": "67.9", "network": "QVC", "call_sign": "QVC"},
        "69.1": {"name": "WAMI-DT", "number": "69.1", "network": "MyNetworkTV", "call_sign": "WAMI-DT"},
        "69.2": {"name": "Confess", "number": "69.2", "network": "Court TV", "call_sign": "Confess"},
        "69.3": {"name": "getTV", "number": "69.3", "network": "getTV", "call_sign": "getTV"},
        "69.4": {"name": "BT2", "number": "69.4", "network": "Bounce", "call_sign": "BT2"},
        "69.5": {"name": "QUEST", "number": "69.5", "network": "Quest", "call_sign": "QUEST"}
    }
    return jsonify(channels)

@app.route('/status')
def status():
    """Check EPG status"""
    guide_exists = os.path.exists('/app/guide.xml')
    if guide_exists:
        stat = os.stat('/app/guide.xml')
        last_updated = datetime.fromtimestamp(stat.st_mtime).isoformat()
        size = stat.st_size
    else:
        last_updated = None
        size = 0
    
    return jsonify({
        'guide_exists': guide_exists,
        'last_updated': last_updated,
        'size_bytes': size,
        'status': 'ready' if guide_exists else 'generating'
    })

@app.route('/refresh')
def refresh_guide():
    """Trigger EPG refresh"""
    def run_grabber():
        subprocess.run(['python', '/app/epg_grabber.py'])
    
    thread = threading.Thread(target=run_grabber)
    thread.start()
    
    return jsonify({'message': 'EPG refresh started'})

@app.route('/')
def home():
    """Home page with instructions"""
    return """
    <h1>Miami-Dade/Broward County EPG Server</h1>
    <h2>Available Endpoints:</h2>
    <ul>
        <li><a href="/guide.xml">/guide.xml</a> - XMLTV EPG data for Plex</li>
        <li><a href="/channels">/channels</a> - List of available channels</li>
        <li><a href="/status">/status</a> - EPG generation status</li>
        <li><a href="/refresh">/refresh</a> - Refresh EPG data</li>
    </ul>
    <h2>Plex Setup:</h2>
    <p>Use this URL in Plex: <strong>http://localhost:3333/guide.xml</strong></p>
    """

def periodic_refresh():
    """Deprecated - using scheduler instead"""
    pass

if __name__ == '__main__':
    # Start scheduler in background thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    print("EPG Server starting with automatic 3-hour refresh cycle")
    
    # Start web server
    app.run(host='0.0.0.0', port=8000, debug=False)
