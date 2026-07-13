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
from apify_client import ApifyClient

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

# Initialize Apify client
APIFY_API_KEY = os.getenv('APIFY_API_KEY', '')
apify_client = ApifyClient(APIFY_API_KEY) if APIFY_API_KEY else None


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
        image_url = get_image_url(image_filename)
        google_search_url = f"https://www.google.com/searchbyimage?image_url={urllib.parse.quote(image_url)}"

        results.append({
            'engine': 'Google Images',
            'url': google_search_url,
            'confidence': 95,
            'description': 'Click to search this image on Google Images — broadest web index coverage',
            'source': 'Google',
            'icon': '🔍',
            'type': 'google'
        })
        logger.info(f"Google Images search URL generated")

    except Exception as e:
        logger.error(f"Google search error: {e}")

    return results


def search_tineye_free(image_filename):
    """Generate TinEye reverse search URL (no API key needed)"""
    results = []
    try:
        image_url = get_image_url(image_filename)
        tineye_search_url = f"https://tineye.com/search?url={urllib.parse.quote(image_url)}"

        results.append({
            'engine': 'TinEye',
            'url': tineye_search_url,
            'confidence': 93,
            'description': 'Click to search this image on TinEye — 60B+ images indexed, best for exact repost detection',
            'source': 'TinEye',
            'icon': '🎯',
            'type': 'tineye'
        })
        logger.info(f"TinEye search URL generated")

    except Exception as e:
        logger.error(f"TinEye search error: {e}")

    return results


def search_bing_images(image_filename):
    """Generate Bing Images reverse search URL"""
    results = []
    try:
        image_url = get_image_url(image_filename)
        bing_search_url = f"https://www.bing.com/images/search?view=detailv2&iss=sbiupload&FORM=IRSBIQ&imgurl={urllib.parse.quote(image_url)}"

        results.append({
            'engine': 'Bing Images',
            'url': bing_search_url,
            'confidence': 85,
            'description': 'Click to search this image on Bing Visual Search — good for visual similarity matching',
            'source': 'Bing',
            'icon': '🔎',
            'type': 'bing'
        })
        logger.info(f"Bing Images search URL generated")

    except Exception as e:
        logger.error(f"Bing search error: {e}")

    return results


def search_yandex_images(image_filename):
    """Generate Yandex Images reverse search URL"""
    results = []
    try:
        image_url = get_image_url(image_filename)
        yandex_search_url = f"https://yandex.com/images/search?rdrnd=1&url={urllib.parse.quote(image_url)}"

        results.append({
            'engine': 'Yandex Images',
            'url': yandex_search_url,
            'confidence': 80,
            'description': 'Click to search this image on Yandex — best free engine for facial recognition & cropped images',
            'source': 'Yandex',
            'icon': '🖼️',
            'type': 'yandex'
        })
        logger.info(f"Yandex Images search URL generated")

    except Exception as e:
        logger.error(f"Yandex search error: {e}")

    return results


def search_apify_google_lens(filepath, image_url):
    """Search Google Lens via Apify — covers all social platforms in one call"""
    results = []

    if not apify_client:
        results.append({
            'engine': 'Google Lens (All Social Platforms)',
            'url': f"https://lens.google.com/uploadbyurl?url={urllib.parse.quote(image_url)}",
            'confidence': 92,
            'description': 'Covers Instagram, Facebook, TikTok, Twitter, Pinterest, LinkedIn, Reddit, YouTube & full web — click to search manually',
            'source': 'Google Lens',
            'icon': '🔍',
            'type': 'lens'
        })
        return results

    try:
        logger.info("Uploading image to Apify key-value store...")
        store = apify_client.key_value_stores().get_or_create(name="osint-image-search")
        kvs = apify_client.key_value_store(store['id'])

        with open(filepath, 'rb') as f:
            kvs.set_record("query_image", f.read(), content_type="image/jpeg")

        logger.info("Running Google Lens Apify actor — searching all social platforms...")
        run = apify_client.actor("borderline/google-lens").call(run_input={
            "searchTypes": ["exact-match", "visual-match"],
            "imageKvsRecords": [{
                "key": "query_image",
                "storeId": store['id']
            }],
            "language": "en",
            "maxResults": 30
        })

        items = list(apify_client.dataset(run['defaultDatasetId']).iterate_items())

        if items:
            logger.info(f"Google Lens found {len(items)} matches across social platforms")

            results.append({
                'engine': 'Google Lens — All Results',
                'url': f"https://console.apify.com/storage/datasets/{run['defaultDatasetId']}",
                'confidence': 98,
                'description': f'✅ {len(items)} matches found across Instagram, Facebook, TikTok, Twitter, Pinterest, LinkedIn, Reddit, YouTube & web — click to view all',
                'source': 'Google Lens',
                'icon': '🔍',
                'type': 'lens'
            })

            platform_count = 0
            for item in items:
                if platform_count >= 8:
                    break

                page_url = item.get('pageUrl', '')
                title = item.get('title', '') or item.get('source', 'Web page')
                source_domain = item.get('source', '')

                if page_url and page_url.startswith('http'):
                    platform_count += 1

                    domain = urllib.parse.urlparse(page_url).netloc.lower()
                    icon = '🌐'
                    if 'instagram' in domain:
                        icon = '📷'
                    elif 'facebook' in domain:
                        icon = '📘'
                    elif 'tiktok' in domain:
                        icon = '🎵'
                    elif 'twitter' in domain or 'x.com' in domain:
                        icon = '🐦'
                    elif 'pinterest' in domain:
                        icon = '📌'
                    elif 'linkedin' in domain:
                        icon = '💼'
                    elif 'reddit' in domain:
                        icon = '👽'
                    elif 'youtube' in domain:
                        icon = '▶️'
                    elif 'tumblr' in domain:
                        icon = '📝'
                    elif 'ebay' in domain or 'amazon' in domain:
                        icon = '🛒'

                    platform_name = domain.replace('www.', '').split('.')[0].capitalize()
                    if platform_name == 'X':
                        platform_name = 'Twitter/X'

                    results.append({
                        'engine': f'{platform_name} Match',
                        'url': page_url,
                        'confidence': 90,
                        'description': f'{title[:100]}' if title else f'Found on {domain}',
                        'source': 'Google Lens',
                        'icon': icon,
                        'type': 'lens_match'
                    })

            if len(items) > platform_count:
                results.append({
                    'engine': f'+ {len(items) - platform_count} more matches',
                    'url': f"https://console.apify.com/storage/datasets/{run['defaultDatasetId']}",
                    'confidence': 85,
                    'description': f'View all {len(items)} results including remaining matches',
                    'source': 'Google Lens',
                    'icon': '📋',
                    'type': 'lens_more'
                })
        else:
            results.append({
                'engine': 'Google Lens (All Social Platforms)',
                'url': f"https://lens.google.com/uploadbyurl?url={urllib.parse.quote(image_url)}",
                'confidence': 88,
                'description': 'No automated matches found. Try manual search on Google Lens for better results',
                'source': 'Google Lens',
                'icon': '🔍',
                'type': 'lens'
            })

    except Exception as e:
        logger.error(f"Apify Google Lens error: {e}")
        results.append({
            'engine': 'Google Lens (All Social Platforms)',
            'url': f"https://lens.google.com/uploadbyurl?url={urllib.parse.quote(image_url)}",
            'confidence': 85,
            'description': f'Automated search unavailable ({str(e)[:80]}...). Click to search manually',
            'source': 'Google Lens',
            'icon': '🔍',
            'type': 'lens'
        })

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
        image_data = file.read()

        filename = secure_filename(f"{int(time.time())}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        with open(filepath, 'wb') as f:
            f.write(image_data)

        image_hash = get_image_hash(filepath)
        image_info = get_image_info(filepath)

        img_b64 = base64.b64encode(image_data).decode('utf-8')
        image_url = get_image_url(filename)

        results = []

        # Free search engines
        results.extend(search_google_images(filename))
        results.extend(search_tineye_free(filename))
        results.extend(search_bing_images(filename))
        results.extend(search_yandex_images(filename))

        # Apify Google Lens — covers all social platforms
        apify_results = search_apify_google_lens(filepath, image_url)
        results.extend(apify_results)

        # Manual OSINT resources
        results.append({
            'engine': 'FaceCheck.ID',
            'url': 'https://facecheck.id/',
            'confidence': 70,
            'description': 'Free facial recognition search across social media, news & public records — upload manually',
            'source': 'OSINT',
            'icon': '👤',
            'type': 'osint'
        })

        results.append({
            'engine': 'Social Catfish',
            'url': 'https://socialcatfish.com/reverse-image-search/',
            'confidence': 65,
            'description': 'Reverse image search for social media profiles and catfish detection',
            'source': 'OSINT',
            'icon': '🐟',
            'type': 'osint'
        })

        response = {
            'success': True,
            'preview': f"data:image/jpeg;base64,{img_b64}",
            'filename': filename,
            'image_hash': image_hash,
            'image_info': image_info,
            'image_url': image_url,
            'results': results,
            'total_results': len(results),
            'message': f'Image uploaded successfully! {len(results)} searches available'
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
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = requests.get(image_url, headers=headers, timeout=15)

        if resp.status_code != 200:
            return jsonify({'error': f'Failed to download image: HTTP {resp.status_code}'}), 400

        image_data = resp.content

        filename = secure_filename(f"url_{int(time.time())}.jpg")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        with open(filepath, 'wb') as f:
            f.write(image_data)

        image_hash = get_image_hash(filepath)
        image_info = get_image_info(filepath)
        img_b64 = base64.b64encode(image_data).decode('utf-8')
        public_url = get_image_url(filename)

        results = []
        results.extend(search_google_images(filename))
        results.extend(search_tineye_free(filename))
        results.extend(search_bing_images(filename))
        results.extend(search_yandex_images(filename))

        apify_results = search_apify_google_lens(filepath, public_url)
        results.extend(apify_results)

        results.append({
            'engine': 'FaceCheck.ID',
            'url': 'https://facecheck.id/',
            'confidence': 70,
            'description': 'Free facial recognition search across social media, news & public records — upload manually',
            'source': 'OSINT',
            'icon': '👤',
            'type': 'osint'
        })

        results.append({
            'engine': 'Social Catfish',
            'url': 'https://socialcatfish.com/reverse-image-search/',
            'confidence': 65,
            'description': 'Reverse image search for social media profiles and catfish detection',
            'source': 'OSINT',
            'icon': '🐟',
            'type': 'osint'
        })

        response = {
            'success': True,
            'preview': f"data:image/jpeg;base64,{img_b64}",
            'filename': filename,
            'image_hash': image_hash,
            'image_info': image_info,
            'image_url': public_url,
            'results': results,
            'total_results': len(results),
            'message': f'Image from URL processed! {len(results)} searches available'
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
    app.run(debug=DEBUG, host='0.0.0.0', port=port)            'url': yandex_search_url,
            'confidence': 80,
            'description': 'Click to search this image on Yandex — best free engine for facial recognition & cropped images',
            'source': 'Yandex',
            'icon': '🖼️',
            'type': 'yandex'
        })
        logger.info(f"Yandex Images search URL generated")

    except Exception as e:
        logger.error(f"Yandex search error: {e}")

    return results


def search_apify_google_lens(filepath, image_url):
    """Search Google Lens via Apify — covers all social platforms in one call"""
    results = []

    if not apify_client:
        results.append({
            'engine': 'Google Lens (All Social Platforms)',
            'url': f"https://lens.google.com/uploadbyurl?url={urllib.parse.quote(image_url)}",
            'confidence': 92,
            'description': 'Covers Instagram, Facebook, TikTok, Twitter, Pinterest, LinkedIn, Reddit, YouTube & full web — click to search manually',
            'source': 'Google Lens',
            'icon': '🔍',
            'type': 'lens'
        })
        return results

    try:
        logger.info("Uploading image to Apify key-value store...")
        store = apify_client.key_value_stores().get_or_create(name="osint-image-search")
        kvs = apify_client.key_value_store(store['id'])

        with open(filepath, 'rb') as f:
            kvs.set_record("query_image", f.read(), content_type="image/jpeg")

        logger.info("Running Google Lens Apify actor — searching all social platforms...")
        run = apify_client.actor("borderline/google-lens").call(run_input={
            "searchTypes": ["exact-match", "visual-match"],
            "imageKvsRecords": [{
                "key": "query_image",
                "storeId": store['id']
            }],
            "language": "en",
            "maxResults": 30
        })

        items = list(apify_client.dataset(run['defaultDatasetId']).iterate_items())

        if items:
            logger.info(f"Google Lens found {len(items)} matches across social platforms")

            results.append({
                'engine': 'Google Lens — All Results',
                'url': f"https://console.apify.com/storage/datasets/{run['defaultDatasetId']}",
                'confidence': 98,
                'description': f'✅ {len(items)} matches found across Instagram, Facebook, TikTok, Twitter, Pinterest, LinkedIn, Reddit, YouTube & web — click to view all',
                'source': 'Google Lens',
                'icon': '🔍',
                'type': 'lens'
            })

            platform_count = 0
            for item in items:
                if platform_count >= 8:
                    break

                page_url = item.get('pageUrl', '')
                title = item.get('title', '') or item.get('source', 'Web page')
                source_domain = item.get('source', '')

                if page_url and page_url.startswith('http'):
                    platform_count += 1

                    domain = urllib.parse.urlparse(page_url).netloc.lower()
                    icon = '🌐'
                    if 'instagram' in domain:
                        icon = '📷'
                    elif 'facebook' in domain:
                        icon = '📘'
                    elif 'tiktok' in domain:
                        icon = '🎵'
                    elif 'twitter' in domain or 'x.com' in domain:
                        icon = '🐦'
                    elif 'pinterest' in domain:
                        icon = '📌'
                    elif 'linkedin' in domain:
                        icon = '💼'
                    elif 'reddit' in domain:
                        icon = '👽'
                    elif 'youtube' in domain:
                        icon = '▶️'
                    elif 'tumblr' in domain:
                        icon = '📝'
                    elif 'ebay' in domain or 'amazon' in domain:
                        icon = '🛒'

                    platform_name = domain.replace('www.', '').split('.')[0].capitalize()
                    if platform_name == 'X':
                        platform_name = 'Twitter/X'

                    results.append({
                        'engine': f'{platform_name} Match',
                        'url': page_url,
                        'confidence': 90,
                        'description': f'{title[:100]}' if title else f'Found on {domain}',
                        'source': 'Google Lens',
                        'icon': icon,
                        'type': 'lens_match'
                    })

            if len(items) > platform_count:
                results.append({
                    'engine': f'+ {len(items) - platform_count} more matches',
                    'url': f"https://console.apify.com/storage/datasets/{run['defaultDatasetId']}",
                    'confidence': 85,
                    'description': f'View all {len(items)} results including remaining matches',
                    'source': 'Google Lens',
                    'icon': '📋',
                    'type': 'lens_more'
                })
        else:
            results.append({
                'engine': 'Google Lens (All Social Platforms)',
                'url': f"https://lens.google.com/uploadbyurl?url={urllib.parse.quote(image_url)}",
                'confidence': 88,
                'description': 'No automated matches found. Try manual search on Google Lens for better results',
                'source': 'Google Lens',
                'icon': '🔍',
                'type': 'lens'
            })

    except Exception as e:
        logger.error(f"Apify Google Lens error: {e}")
        results.append({
            'engine': 'Google Lens (All Social Platforms)',
            'url': f"https://lens.google.com/uploadbyurl?url={urllib.parse.quote(image_url)}",
            'confidence': 85,
            'description': f'Automated search unavailable ({str(e)[:80]}...). Click to search manually',
            'source': 'Google Lens',
            'icon': '🔍',
            'type': 'lens'
        })

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
        image_data = file.read()

        filename = secure_filename(f"{int(time.time())}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        with open(filepath, 'wb') as f:
            f.write(image_data)

        image_hash = get_image_hash(filepath)
        image_info = get_image_info(filepath)

        img_b64 = base64.b64encode(image_data).decode('utf-8')
        image_url = get_image_url(filename)

        results = []

        # Free search engines
        results.extend(search_google_images(filename))
        results.extend(search_tineye_free(filename))
        results.extend(search_bing_images(filename))
        results.extend(search_yandex_images(filename))

        # Apify Google Lens — covers all social platforms
        apify_results = search_apify_google_lens(filepath, image_url)
        results.extend(apify_results)

        # Manual OSINT resources
        results.append({
            'engine': 'FaceCheck.ID',
            'url': 'https://facecheck.id/',
            'confidence': 70,
            'description': 'Free facial recognition search across social media, news & public records — upload manually',
            'source': 'OSINT',
            'icon': '👤',
            'type': 'osint'
        })

        results.append({
            'engine': 'Social Catfish',
            'url': 'https://socialcatfish.com/reverse-image-search/',
            'confidence': 65,
            'description': 'Reverse image search for social media profiles and catfish detection',
            'source': 'OSINT',
            'icon': '🐟',
            'type': 'osint'
        })

        response = {
            'success': True,
            'preview': f"data:image/jpeg;base64,{img_b64}",
            'filename': filename,
            'image_hash': image_hash,
            'image_info': image_info,
            'image_url': image_url,
            'results': results,
            'total_results': len(results),
            'message': f'Image uploaded successfully! {len(results)} searches available'
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
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = requests.get(image_url, headers=headers, timeout=15)

        if resp.status_code != 200:
            return jsonify({'error': f'Failed to download image: HTTP {resp.status_code}'}), 400

        image_data = resp.content

        filename = secure_filename(f"url_{int(time.time())}.jpg")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        with open(filepath, 'wb') as f:
            f.write(image_data)

        image_hash = get_image_hash(filepath)
        image_info = get_image_info(filepath)
        img_b64 = base64.b64encode(image_data).decode('utf-8')
        public_url = get_image_url(filename)

        results = []
        results.extend(search_google_images(filename))
        results.extend(search_tineye_free(filename))
        results.extend(search_bing_images(filename))
        results.extend(search_yandex_images(filename))

        apify_results = search_apify_google_lens(filepath, public_url)
        results.extend(apify_results)

        results.append({
            'engine': 'FaceCheck.ID',
            'url': 'https://facecheck.id/',
            'confidence': 70,
            'description': 'Free facial recognition search across social media, news & public records — upload manually',
            'source': 'OSINT',
            'icon': '👤',
            'type': 'osint'
        })

        results.append({
            'engine': 'Social Catfish',
            'url': 'https://socialcatfish.com/reverse-image-search/',
            'confidence': 65,
            'description': 'Reverse image search for social media profiles and catfish detection',
            'source': 'OSINT',
            'icon': '🐟',
            'type': 'osint'
        })

        response = {
            'success': True,
            'preview': f"data:image/jpeg;base64,{img_b64}",
            'filename': filename,
            'image_hash': image_hash,
            'image_info': image_info,
            'image_url': public_url,
            'results': results,
            'total_results': len(results),
            'message': f'Image from URL processed! {len(results)} searches available'
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
