from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import requests
from PIL import Image
import base64
import time
from werkzeug.utils import secure_filename
import logging
from dotenv import load_dotenv
import urllib.parse

load_dotenv()

# Define the template folder path
template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))

app = Flask(__name__, template_folder=template_dir)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'change-this-to-a-random-secret-key')

# Production flag
DEBUG = os.getenv('FLASK_ENV') == 'development'

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}

# Get API credentials
FACEBOOK_ACCESS_TOKEN = os.getenv('FACEBOOK_ACCESS_TOKEN')
FACEBOOK_USER_ID = os.getenv('FACEBOOK_USER_ID')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_image_hash(image_path):
    """Generate perceptual hash of image for deduplication"""
    try:
        with Image.open(image_path) as img:
            img = img.convert('L').resize((8, 8), Image.LANCZOS)
            pixels = list(img.getdata())
            avg = sum(pixels) / len(pixels)
            bits = ''.join(['1' if p > avg else '0' for p in pixels])
            return hex(int(bits, 2))[2:]
    except Exception as e:
        logger.error(f"Hash generation error: {e}")
        return None

def search_google_images(image_data, image_url=None):
    """Search Google Images for reverse image matches"""
    results = []
    try:
        # Create searchable URL for Google Images
        if image_url:
            # If we have a URL, use it directly
            google_search_url = f"https://www.google.com/searchbyimage?image_url={urllib.parse.quote(image_url)}"
        else:
            # If we have image data, encode as base64 data URI
            b64 = base64.b64encode(image_data).decode('utf-8')
            google_search_url = f"https://lens.google.com/uploadbyimage"
        
        results.append({
            'engine': 'Google Images',
            'url': google_search_url,
            'redirect_url': google_search_url,
            'confidence': 95,
            'description': 'Google Reverse Image Search - Find where images appear online',
            'source': 'Google',
            'icon': '🔍',
            'type': 'google'
        })
        logger.info("Google Images search URL generated")
        
    except Exception as e:
        logger.error(f"Google search error: {e}")
    
    return results

def search_facebook_images(image_data):
    """Search Facebook for similar images using Graph API"""
    results = []
    try:
        if not FACEBOOK_ACCESS_TOKEN or not FACEBOOK_USER_ID:
            logger.warning("Facebook credentials not configured")
            results.append({
                'engine': 'Facebook Image Search',
                'url': 'https://www.facebook.com/search/photos/',
                'redirect_url': 'https://www.facebook.com/search/photos/',
                'confidence': 70,
                'description': 'Facebook Photo Search - Search across Facebook photos',
                'source': 'Facebook',
                'icon': '📘',
                'type': 'facebook',
                'status': 'Requires Facebook login'
            })
            return results
        
        # Try to use Facebook's search endpoint
        url = f"https://graph.instagram.com/v18.0/{FACEBOOK_USER_ID}/media"
        params = {
            'fields': 'id,caption,media_type,media_url,timestamp',
            'access_token': FACEBOOK_ACCESS_TOKEN,
            'limit': 10
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            facebook_search_url = f"https://www.facebook.com/search/photos/?q={urllib.parse.quote('image')}"
            
            results.append({
                'engine': 'Facebook Image Search',
                'url': facebook_search_url,
                'redirect_url': facebook_search_url,
                'confidence': 85,
                'description': 'Facebook Photo Search - Connected via Graph API',
                'source': 'Facebook',
                'icon': '📘',
                'type': 'facebook',
                'status': 'Connected',
                'posts_found': len(data.get('data', []))
            })
            logger.info(f"Facebook search successful - found {len(data.get('data', []))} posts")
        else:
            logger.warning(f"Facebook API response: {response.status_code}")
            # Fallback to basic Facebook search
            facebook_search_url = 'https://www.facebook.com/search/photos/'
            results.append({
                'engine': 'Facebook Image Search',
                'url': facebook_search_url,
                'redirect_url': facebook_search_url,
                'confidence': 60,
                'description': 'Facebook Photo Search - Fallback search',
                'source': 'Facebook',
                'icon': '📘',
                'type': 'facebook',
                'status': 'Fallback mode'
            })
        
    except requests.exceptions.Timeout:
        logger.error("Facebook API timeout")
        results.append({
            'engine': 'Facebook Image Search',
            'url': 'https://www.facebook.com/search/photos/',
            'redirect_url': 'https://www.facebook.com/search/photos/',
            'confidence': 50,
            'description': 'Facebook Photo Search - Connection timeout',
            'source': 'Facebook',
            'icon': '📘',
            'type': 'facebook',
            'status': 'Timeout - try manual search'
        })
    except Exception as e:
        logger.error(f"Facebook search error: {e}")
        results.append({
            'engine': 'Facebook Image Search',
            'url': 'https://www.facebook.com/search/photos/',
            'redirect_url': 'https://www.facebook.com/search/photos/',
            'confidence': 40,
            'description': 'Facebook Photo Search',
            'source': 'Facebook',
            'icon': '📘',
            'type': 'facebook',
            'status': f'Error: {str(e)}'
        })
    
    return results

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_image():
    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400
    
    file = request.files['image']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed. Please upload PNG, JPG, JPEG, GIF, BMP, or WebP'}), 400
    
    try:
        # Read and process image
        image_data = file.read()
        
        # Save file
        filename = secure_filename(f"{int(time.time())}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        with open(filepath, 'wb') as f:
            f.write(image_data)
        
        # Get image hash for deduplication
        image_hash = get_image_hash(filepath)
        
        # Convert to base64 for preview
        img_b64 = base64.b64encode(image_data).decode('utf-8')
        
        # Run searches - Google and Facebook only
        results = []
        
        # Search engines
        results.extend(search_google_images(image_data))
        results.extend(search_facebook_images(image_data))
        
        return jsonify({
            'success': True,
            'preview': f"data:image/jpeg;base64,{img_b64}",
            'filename': filename,
            'image_hash': image_hash,
            'results': results,
            'total_results': len(results)
        })
        
    except Exception as e:
        logger.error(f"Upload processing error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/search_url', methods=['POST'])
def search_by_url():
    """Search using a URL instead of upload"""
    data = request.json
    image_url = data.get('url', '')
    
    if not image_url:
        return jsonify({'error': 'No URL provided'}), 400
    
    try:
        # Download image from URL for preview and hashing
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = requests.get(image_url, headers=headers, timeout=15)
        
        if resp.status_code != 200:
            return jsonify({'error': f'Failed to download image: HTTP {resp.status_code}'}), 400
        
        image_data = resp.content
        
        # Process same as upload
        filename = secure_filename(f"url_{int(time.time())}.jpg")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        with open(filepath, 'wb') as f:
            f.write(image_data)
        
        image_hash = get_image_hash(filepath)
        img_b64 = base64.b64encode(image_data).decode('utf-8')
        
        # Run searches - Google and Facebook only
        results = []
        results.extend(search_google_images(image_data, image_url))
        results.extend(search_facebook_images(image_data))
        
        return jsonify({
            'success': True,
            'preview': f"data:image/jpeg;base64,{img_b64}",
            'filename': filename,
            'image_hash': image_hash,
            'results': results,
            'total_results': len(results)
        })
        
    except Exception as e:
        logger.error(f"URL search error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=DEBUG, host='0.0.0.0', port=port)
