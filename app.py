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
import io

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

def get_image_url(filename):
    """Get the URL for an uploaded image"""
    base_url = os.getenv('BASE_URL', 'https://pimeye.onrender.com')
    return f"{base_url}/uploads/{filename}"

def search_google_images(image_filename):
    """Generate Google Images reverse search URL"""
    results = []
    try:
        # Get the image URL
        image_url = get_image_url(image_filename)
        
        # Create Google Images reverse search URL
        google_search_url = f"https://www.google.com/searchbyimage?image_url={urllib.parse.quote(image_url)}"
        
        results.append({
            'engine': 'Google Images',
            'url': google_search_url,
            'confidence': 95,
            'description': 'Click to search this image on Google Images',
            'source': 'Google',
            'icon': '🔍',
            'type': 'google',
            'status': 'Ready to search'
        })
        logger.info(f"Google Images search URL generated: {google_search_url}")
        
    except Exception as e:
        logger.error(f"Google search error: {e}")
    
    return results

def search_tineye_free(image_filename):
    """Generate TinEye reverse search URL (no API key needed)"""
    results = []
    try:
        # Get the image URL
        image_url = get_image_url(image_filename)
        
        # Create TinEye reverse search URL
        tineye_search_url = f"https://tineye.com/search?url={urllib.parse.quote(image_url)}"
        
        results.append({
            'engine': 'TinEye',
            'url': tineye_search_url,
            'confidence': 90,
            'description': 'Click to search this image on TinEye - finds where images appear online',
            'source': 'TinEye',
            'icon': '🎯',
            'type': 'tineye',
            'status': 'Ready to search'
        })
        logger.info(f"TinEye search URL generated: {tineye_search_url}")
        
    except Exception as e:
        logger.error(f"TinEye search error: {e}")
    
    return results

def search_bing_images(image_filename):
    """Generate Bing Images reverse search URL"""
    results = []
    try:
        # Get the image URL
        image_url = get_image_url(image_filename)
        
        # Create Bing Images reverse search URL
        bing_search_url = f"https://www.bing.com/images/search?view=detailv2&iss=sbiupload&FORM=IRSBIQ&imgurl={urllib.parse.quote(image_url)}"
        
        results.append({
            'engine': 'Bing Images',
            'url': bing_search_url,
            'confidence': 85,
            'description': 'Click to search this image on Bing Images',
            'source': 'Bing',
            'icon': '🔎',
            'type': 'bing',
            'status': 'Ready to search'
        })
        logger.info(f"Bing Images search URL generated: {bing_search_url}")
        
    except Exception as e:
        logger.error(f"Bing search error: {e}")
    
    return results

def search_yandex_images(image_filename):
    """Generate Yandex Images reverse search URL"""
    results = []
    try:
        # Get the image URL
        image_url = get_image_url(image_filename)
        
        # Create Yandex Images reverse search URL
        yandex_search_url = f"https://yandex.com/images/search?rdrnd=1&url={urllib.parse.quote(image_url)}"
        
        results.append({
            'engine': 'Yandex Images',
            'url': yandex_search_url,
            'confidence': 80,
            'description': 'Click to search this image on Yandex Images',
            'source': 'Yandex',
            'icon': '🖼️',
            'type': 'yandex',
            'status': 'Ready to search'
        })
        logger.info(f"Yandex Images search URL generated: {yandex_search_url}")
        
    except Exception as e:
        logger.error(f"Yandex search error: {e}")
    
    return results

def get_image_info(filepath):
    """Extract image information and metadata"""
    try:
        with Image.open(filepath) as img:
            info = {
                'format': img.format,
                'mode': img.mode,
                'size': f"{img.width} x {img.height}",
                'dimensions': {'width': img.width, 'height': img.height}
            }
            return info
    except Exception as e:
        logger.error(f"Image info error: {e}")
        return {}

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
        
        # Get image hash and info
        image_hash = get_image_hash(filepath)
        image_info = get_image_info(filepath)
        
        # Convert to base64 for preview
        img_b64 = base64.b64encode(image_data).decode('utf-8')
        
        # Run searches - Free providers only, no API keys needed
        results = []
        
        # Add all free reverse image search engines
        results.extend(search_google_images(filename))
        results.extend(search_tineye_free(filename))
        results.extend(search_bing_images(filename))
        results.extend(search_yandex_images(filename))
        
        response = {
            'success': True,
            'preview': f"data:image/jpeg;base64,{img_b64}",
            'filename': filename,
            'image_hash': image_hash,
            'image_info': image_info,
            'image_url': get_image_url(filename),
            'results': results,
            'total_results': len(results),
            'message': f'Image uploaded successfully! {len(results)} search engines available'
        }
        
        logger.info(f"Image uploaded: {filename} - {len(results)} searches available")
        return jsonify(response)
        
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
        # Download image from URL for preview
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = requests.get(image_url, headers=headers, timeout=15)
        
        if resp.status_code != 200:
            return jsonify({'error': f'Failed to download image: HTTP {resp.status_code}'}), 400
        
        image_data = resp.content
        
        # Save locally
        filename = secure_filename(f"url_{int(time.time())}.jpg")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        with open(filepath, 'wb') as f:
            f.write(image_data)
        
        image_hash = get_image_hash(filepath)
        image_info = get_image_info(filepath)
        img_b64 = base64.b64encode(image_data).decode('utf-8')
        
        # Run searches
        results = []
        results.extend(search_google_images(filename))
        results.extend(search_tineye_free(filename))
        results.extend(search_bing_images(filename))
        results.extend(search_yandex_images(filename))
        
        response = {
            'success': True,
            'preview': f"data:image/jpeg;base64,{img_b64}",
            'filename': filename,
            'image_hash': image_hash,
            'image_info': image_info,
            'image_url': get_image_url(filename),
            'results': results,
            'total_results': len(results),
            'message': f'Image from URL processed! {len(results)} search engines available'
        }
        
        logger.info(f"URL image processed: {filename} - {len(results)} searches available")
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"URL search error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded images"""
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except Exception as e:
        logger.error(f"File serve error: {e}")
        return jsonify({'error': 'File not found'}), 404

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=DEBUG, host='0.0.0.0', port=port)
