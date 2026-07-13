# OSINT Image Tracker - Pimeye

A Flask-based reverse image search tool that integrates with multiple search engines, social media platforms, and OSINT databases to track and locate images across the internet.

## Features

🔍 **Multi-Engine Search**
- Google Images
- Yandex Images
- Bing Visual Search
- TinEye

📱 **Social Media Search**
- Facebook
- Twitter/X
- LinkedIn
- Instagram
- Reddit
- Pinterest
- TikTok

🛡️ **OSINT Database Integration**
- PimEyes (Facial Recognition)
- Social Catfish
- Search4Faces
- FaceCheck.ID
- Have I Been Pwned

## Local Development

### Prerequisites
- Python 3.9+
- pip

### Installation

1. Clone the repository
```bash
git clone https://github.com/devismwanzi502-debug/Pimeye.git
cd Pimeye
```

2. Create a virtual environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Run the application
```bash
python app.py
```

The application will be available at `http://localhost:5000`

## Deployment on Render

### Quick Deploy

1. Go to [Render.com](https://render.com)
2. Create a new Web Service
3. Connect your GitHub repository
4. Render will auto-detect the `render.yaml` configuration
5. Click "Deploy"

### Manual Configuration

If auto-detection doesn't work:

- **Runtime**: Python
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn app:app`
- **Environment Variables**:
  - `FLASK_ENV`: `production`
  - `SECRET_KEY`: Your secret key (generate one)

## Usage

1. **Upload an Image**
   - Click "Choose Image" or drag and drop
   - Supported formats: JPG, PNG, GIF, BMP, WebP

2. **Search by URL**
   - Paste an image URL and click "Search URL"

3. **View Results**
   - Results from search engines and OSINT databases
   - Click "View Source" to visit the original location

4. **Export Results**
   - Click "Export CSV" to download search results

## API Endpoints

- `GET /` - Main page
- `POST /upload` - Upload and search an image
- `POST /search_url` - Search by image URL
- `GET /uploads/<filename>` - Access uploaded files

## Project Structure

```
Pimeye/
├── app.py              # Flask application
├── requirements.txt    # Python dependencies
├── Procfile           # Deployment configuration
├── render.yaml        # Render service configuration
├── .gitignore         # Git ignore rules
└── templates/
    └── index.html     # Frontend UI
```

## Environment Variables

- `FLASK_ENV` - Set to `production` for Render
- `PORT` - Port number (default: 5000, Render: 10000)
- `SECRET_KEY` - Flask secret key for session management

## License

This project is for authorized security testing and educational purposes only.

## Author

[devismwanzi502-debug](https://github.com/devismwanzi502-debug)
