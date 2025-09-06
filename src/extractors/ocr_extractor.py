#!/usr/bin/env python3
"""
OCR-based attendance code extractor with support for multiple AI vision APIs
"""

import os
import base64
import re
import json
import asyncio
import hashlib
import tempfile
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from urllib.parse import urlparse
import mimetypes

import aiohttp
from playwright.async_api import Page

from utils.logger import logger


class OCRCodeExtractor:
    """Extract attendance codes from images using AI vision APIs"""
    
    def __init__(self):
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.repo_owner = os.getenv("REPO_OWNER", "bunizao")
        self.repo_name = os.getenv("REPO_NAME", "always-attend")
        
        # OCR Cache settings
        self.cache_dir = os.path.join(tempfile.gettempdir(), "always_attend_ocr_cache")
        self.cache_ttl_hours = int(os.getenv("OCR_CACHE_TTL_HOURS", "24"))  # Cache for 24 hours by default
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Attendance code patterns
        self.code_patterns = [
            r'\b([A-Z0-9]{4,8})\b',  # General alphanumeric codes
            r'code[:\s]+([A-Z0-9]{4,8})',  # "code: ABC123"
            r'attendance[:\s]+([A-Z0-9]{4,8})',  # "attendance: ABC123"
        ]
        
        # Words to exclude from code detection
        self.exclude_words = {
            'HTTP', 'HTTPS', 'NULL', 'TRUE', 'FALSE', 'TEST', 'DEMO',
            'ADMIN', 'USER', 'LOGIN', 'PASSWORD', 'EMAIL', 'NAME',
            'DATE', 'TIME', 'YEAR', 'WEEK', 'DAY', 'MONTH'
        }

    def purge_cache(self) -> None:
        """Purge all cached OCR results and downloaded images"""
        try:
            if os.path.exists(self.cache_dir):
                import shutil
                shutil.rmtree(self.cache_dir)
                os.makedirs(self.cache_dir, exist_ok=True)
                logger.info(f"Cache purged: {self.cache_dir}")
            else:
                logger.info("Cache directory does not exist, nothing to purge")
        except Exception as e:
            logger.warning(f"Error purging cache: {e}")

    def _get_image_hash(self, image_url: str) -> str:
        """Generate a hash for image URL to use as cache key"""
        return hashlib.md5(image_url.encode()).hexdigest()

    def _get_cache_path(self, image_hash: str) -> str:
        """Get cache file path for an image hash"""
        return os.path.join(self.cache_dir, f"{image_hash}.json")

    def _is_cache_valid(self, cache_path: str) -> bool:
        """Check if cache file exists and is within TTL"""
        if not os.path.exists(cache_path):
            return False
        
        try:
            stat = os.stat(cache_path)
            cache_age = datetime.now() - datetime.fromtimestamp(stat.st_mtime)
            return cache_age < timedelta(hours=self.cache_ttl_hours)
        except Exception:
            return False

    def _load_from_cache(self, image_hash: str) -> Optional[List[str]]:
        """Load OCR results from cache if available and valid"""
        cache_path = self._get_cache_path(image_hash)
        
        if not self._is_cache_valid(cache_path):
            return None
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                logger.debug(f"Cache hit for image {image_hash[:8]}...")
                return cache_data.get('codes', [])
        except Exception as e:
            logger.debug(f"Cache read error for {image_hash[:8]}: {e}")
            return None

    def _save_to_cache(self, image_hash: str, codes: List[str]) -> None:
        """Save OCR results to cache"""
        cache_path = self._get_cache_path(image_hash)
        
        try:
            cache_data = {
                'codes': codes,
                'timestamp': datetime.now().isoformat(),
                'image_hash': image_hash
            }
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
                
            logger.debug(f"Cached {len(codes)} codes for image {image_hash[:8]}...")
        except Exception as e:
            logger.debug(f"Cache write error for {image_hash[:8]}: {e}")

    def _cleanup_old_cache(self) -> None:
        """Clean up old cache files"""
        try:
            now = datetime.now()
            ttl = timedelta(hours=self.cache_ttl_hours)
            
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.json'):
                    filepath = os.path.join(self.cache_dir, filename)
                    try:
                        stat = os.stat(filepath)
                        if now - datetime.fromtimestamp(stat.st_mtime) > ttl:
                            os.remove(filepath)
                            logger.debug(f"Removed expired cache file: {filename}")
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"Cache cleanup error: {e}")

    async def detect_images_in_gmail(self, page: Page) -> List[Dict[str, str]]:
        """Detect images in Gmail emails that might contain attendance codes"""
        images = []
        
        try:
            # Strategy: prefer original links that end with .png from learning.monash.edu
            # 1) Anchor tags with href ending in .png
            anchor_selectors = [
                'a[href*="learning.monash.edu"][href$=".png"]',
                'a[href$=".png"]',
            ]
            for selector in anchor_selectors:
                try:
                    anchors = page.locator(selector)
                    n = await anchors.count()
                    for i in range(n):
                        href = await anchors.nth(i).get_attribute('href')
                        if not href:
                            continue
                        fixed_href = self._fix_learning_monash_url(href)
                        if fixed_href.lower().endswith('.png'):
                            images.append({'src': fixed_href, 'original_src': href, 'alt': ''})
                except Exception:
                    pass

            # 2) As fallback, scan img tags but require .png
            img_selectors = [
                'img[src$=".png"]',
                'img[src*="learning.monash.edu"][src*=".png"]',
                'img[src*="monash.edu"][src*=".png"]',
            ]
            for selector in img_selectors:
                try:
                    img_elements = page.locator(selector)
                    count = await img_elements.count()
                    for i in range(count):
                        img = img_elements.nth(i)
                        src = await img.get_attribute('src')
                        alt = await img.get_attribute('alt') or ""
                        if not src:
                            continue
                        if not src.lower().endswith('.png'):
                            continue
                        fixed_src = self._fix_learning_monash_url(src)
                        images.append({'src': fixed_src, 'original_src': src, 'alt': alt})
                except Exception:
                    pass
        
        except Exception as e:
            logger.warning(f"Error detecting images in Gmail: {e}")
            
        logger.info(f"Found {len(images)} potential attendance code images")
        return images

    def _fix_learning_monash_url(self, url: str) -> str:
        """Fix soft-wrap artifacts in learning.monash.edu URLs (remove '=' and newlines)."""
        if "learning.monash.edu" in url:
            fixed = url.replace("\n", "").replace("\r", "")
            # Remove soft-wrap '=' characters common in quoted-printable emails
            fixed = fixed.replace("=", "")
            if fixed != url:
                logger.debug(f"Fixed learning.monash.edu URL: {url} -> {fixed}")
            return fixed
        return url

    def _is_likely_attendance_image(self, src: str, alt: str) -> bool:
        """Check if an image is likely to contain attendance codes"""
        # Prioritize learning.monash.edu .png files (user specified these are correct)
        if "learning.monash.edu" in src.lower() and src.lower().endswith('.png'):
            logger.debug(f"High priority image found: {src}")
            return True
            
        # Also accept other Monash .png files
        if "monash.edu" in src.lower() and src.lower().endswith('.png'):
            return True
        
        # Skip very small images, icons, and logos
        if any(keyword in src.lower() for keyword in ['icon', 'logo', 'avatar', 'profile']):
            return False
            
        if any(keyword in alt.lower() for keyword in ['icon', 'logo', 'avatar', 'profile']):
            return False
            
        # Look for attendance-related keywords
        attendance_keywords = ['code', 'attendance', 'workshop', 'tutorial', 'lab', 'session']
        if any(keyword in alt.lower() for keyword in attendance_keywords):
            return True
            
        # Only accept PNG per user instruction
        if not src.lower().endswith('.png'):
            return False
        return True

    async def download_and_rename_image(self, image_info: Dict[str, Any], course_code: str = None, week_number: str = None) -> Optional[str]:
        """Download image and save it with a proper filename for OCR processing"""
        try:
            src = image_info['src']
            logger.info(f"Downloading image: {src}")
            
            # Download the image
            result = await self.download_image(src)
            if not result:
                logger.warning(f"Failed to download image: {src}")
                return None
                
            image_data, content_type = result
            
            # Generate a meaningful filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_hash = hashlib.md5(image_data).hexdigest()[:8]
            
            # Extract file extension from URL or content type
            if src.lower().endswith('.png'):
                ext = 'png'
            elif src.lower().endswith('.jpg') or src.lower().endswith('.jpeg'):
                ext = 'jpg'
            elif 'png' in content_type:
                ext = 'png'
            elif 'jpeg' in content_type:
                ext = 'jpg'
            else:
                ext = 'png'  # Default to PNG
            
            # Create filename with course and week info if available
            if course_code and week_number:
                filename = f"{course_code}_week{week_number}_{timestamp}_{image_hash}.{ext}"
            else:
                filename = f"attendance_code_{timestamp}_{image_hash}.{ext}"
            
            # Save to cache directory
            image_path = os.path.join(self.cache_dir, filename)
            with open(image_path, 'wb') as f:
                f.write(image_data)
            
            logger.info(f"Image saved as: {filename}")
            return image_path
            
        except Exception as e:
            logger.warning(f"Error downloading and renaming image: {e}")
            return None

    async def download_image(self, image_url: str) -> Optional[Tuple[bytes, str]]:
        """Download image from URL and return bytes with mime type"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        content_type = response.headers.get('content-type', 'image/jpeg')
                        
                        # Validate image size (limit to 20MB)
                        if len(image_data) > 20 * 1024 * 1024:
                            logger.warning(f"Image too large: {len(image_data)} bytes")
                            return None
                        
                        # Validate minimum size (at least 1KB)
                        if len(image_data) < 1024:
                            logger.warning(f"Image too small: {len(image_data)} bytes")
                            return None
                            
                        return image_data, content_type
        except Exception as e:
            logger.warning(f"Failed to download image {image_url}: {e}")
        return None

    async def extract_with_gemini(self, image_data: bytes, mime_type: str = "image/jpeg") -> List[str]:
        """Extract text from image using Google Gemini Vision API"""
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not configured")
            
        try:
            # Validate and normalize mime type
            if not mime_type or mime_type not in ['image/jpeg', 'image/png', 'image/webp', 'image/gif']:
                mime_type = "image/jpeg"
            
            # Encode image to base64
            image_b64 = base64.b64encode(image_data).decode('utf-8')
            
            # Validate base64 encoding
            if not image_b64:
                logger.warning("Failed to encode image to base64")
                return []
            
            # Prepare Gemini API request
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"
            
            payload = {
                "contents": [{
                    "parts": [
                        {
                            "text": """Extract any attendance codes from this image. Look for:
1. Short alphanumeric codes (4-8 characters) that might be attendance codes
2. Any text that says "code", "attendance code", "workshop code", etc.
3. QR codes or barcodes (describe what you see)

Return only the codes found, one per line. If no codes are found, return "NO_CODES_FOUND"."""
                        },
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": image_b64
                            }
                        }
                    ]
                }],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 256
                }
            }
            
            timeout = aiohttp.ClientTimeout(total=30)  # 30 second timeout
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                        return self._extract_codes_from_text(text)
                    else:
                        error_text = await response.text()
                        logger.warning(f"Gemini API error: {response.status} - {error_text}")
                        
                        # Try fallback with different settings if it's a client error
                        if response.status == 400:
                            logger.info("Retrying with simplified request...")
                            return await self._retry_gemini_simple(image_data, mime_type)
                        
        except asyncio.TimeoutError:
            logger.warning("Gemini API request timed out")
        except Exception as e:
            logger.warning(f"Gemini OCR failed: {e}")
            
        return []

    async def _retry_gemini_simple(self, image_data: bytes, mime_type: str) -> List[str]:
        """Retry Gemini with simplified settings for problematic images"""
        try:
            image_b64 = base64.b64encode(image_data).decode('utf-8')
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"
            
            # Simpler payload with minimal configuration
            payload = {
                "contents": [{
                    "parts": [
                        {
                            "text": "Extract any attendance codes from this image. Return only the codes found."
                        },
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": image_b64
                            }
                        }
                    ]
                }]
            }
            
            timeout = aiohttp.ClientTimeout(total=15)  # Shorter timeout for retry
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                        return self._extract_codes_from_text(text)
                    else:
                        error_text = await response.text()
                        logger.warning(f"Gemini retry failed: {response.status} - {error_text}")
                        
        except Exception as e:
            logger.warning(f"Gemini retry failed: {e}")
            
        return []

    async def extract_with_openai(self, image_data: bytes) -> List[str]:
        """Extract text from image using OpenAI Vision API"""
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY not configured")
            
        try:
            # Encode image to base64
            image_b64 = base64.b64encode(image_data).decode('utf-8')
            
            # Prepare OpenAI API request
            url = "https://api.openai.com/v1/chat/completions"
            
            headers = {
                "Authorization": f"Bearer {self.openai_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "gpt-4o-mini",  # Use the more cost-effective vision model
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": """Extract any attendance codes from this image. Look for:
1. Short alphanumeric codes (4-8 characters) that might be attendance codes
2. Any text that says "code", "attendance code", "workshop code", etc.
3. QR codes or barcodes (describe what you see)

Return only the codes found, one per line. If no codes are found, return "NO_CODES_FOUND"."""
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 300
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        text = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                        return self._extract_codes_from_text(text)
                    else:
                        error_text = await response.text()
                        logger.warning(f"OpenAI API error: {response.status} - {error_text}")
                        
        except Exception as e:
            logger.warning(f"OpenAI OCR failed: {e}")
            
        return []

    def _extract_codes_from_text(self, text: str) -> List[str]:
        """Extract valid attendance codes from OCR text"""
        if "NO_CODES_FOUND" in text.upper():
            return []
            
        codes = []
        for pattern in self.code_patterns:
            matches = re.findall(pattern, text.upper())
            for match in matches:
                if self._is_valid_attendance_code(match):
                    codes.append(match)
                    
        return list(set(codes))  # Remove duplicates

    def _is_valid_attendance_code(self, code: str) -> bool:
        """Validate if a code looks like a real attendance code"""
        if not code or len(code) < 4 or len(code) > 8:
            return False
            
        if code.upper() in self.exclude_words:
            return False
            
        # Must contain at least one letter and one number for most attendance codes
        has_letter = any(c.isalpha() for c in code)
        has_number = any(c.isdigit() for c in code)
        
        # Accept codes with only letters or only numbers if they're the right length
        return (has_letter or has_number) and len(code) >= 4

    async def create_github_issue(self, images: List[Dict[str, str]], course_code: str = None) -> Optional[str]:
        """Create GitHub issue with image links for manual processing"""
        if not self.github_token:
            logger.warning("No GITHUB_TOKEN configured, cannot create issue")
            return None
            
        try:
            url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/issues"
            
            headers = {
                "Authorization": f"token {self.github_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            # Create issue body with image links
            body_lines = [
                "## 📧 Attendance Code Images Detected",
                "",
                "The following images were found in Gmail that may contain attendance codes:",
                ""
            ]
            
            if course_code:
                body_lines.append(f"**Course:** {course_code}")
                body_lines.append("")
            
            for i, img in enumerate(images, 1):
                body_lines.extend([
                    f"### Image {i}",
                    f"- **Source:** {img['src']}",
                    f"- **Alt text:** {img.get('alt', 'N/A')}",
                    f"- **Dimensions:** {img.get('width', '?')}x{img.get('height', '?')}",
                    "",
                    f"![Attendance Code Image {i}]({img['src']})",
                    ""
                ])
            
            body_lines.extend([
                "---",
                "",
                "Please extract the attendance codes from these images and add them to the appropriate data files.",
                "",
                "🤖 *This issue was created automatically by Always Attend*"
            ])
            
            payload = {
                "title": f"Attendance Code Images - {course_code or 'Unknown Course'}",
                "body": "\n".join(body_lines),
                "labels": ["attendance-codes", "images", "manual-review"]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 201:
                        result = await response.json()
                        issue_url = result.get('html_url')
                        logger.info(f"Created GitHub issue: {issue_url}")
                        return issue_url
                    else:
                        error_text = await response.text()
                        logger.warning(f"Failed to create GitHub issue: {response.status} - {error_text}")
                        
        except Exception as e:
            logger.warning(f"Error creating GitHub issue: {e}")
            
        return None

    async def extract_codes_from_images(self, images: List[Dict[str, str]], 
                                      preferred_method: str = "auto") -> List[Dict[str, Any]]:
        """Extract attendance codes from a list of images"""
        extracted_codes = []
        
        # Clean up old cache files at the start
        self._cleanup_old_cache()
        
        for i, image_info in enumerate(images):
            logger.info(f"Processing image {i+1}/{len(images)}: {image_info['src'][:100]}...")
            
            try:
                image_url = image_info['src']
                image_hash = self._get_image_hash(image_url)
                
                # Try to load from cache first
                cached_codes = self._load_from_cache(image_hash)
                if cached_codes is not None:
                    logger.info(f"Using cached result for image {i+1}: {len(cached_codes)} codes")
                    for code in cached_codes:
                        extracted_codes.append({
                            'code': code,
                            'source': 'ocr_cached',
                            'method': 'cached',
                            'image_url': image_url,
                            'image_alt': image_info.get('alt', ''),
                            'confidence': 'cached'
                        })
                    continue
                
                # Download the image if not in cache
                download_result = await self.download_image(image_url)
                if not download_result:
                    continue
                
                image_data, mime_type = download_result
                codes = []
                
                # Try extraction based on preferred method
                if preferred_method == "auto":
                    # Try Gemini first, then OpenAI, then GitHub issue
                    if self.gemini_api_key:
                        codes = await self.extract_with_gemini(image_data, mime_type)
                    elif self.openai_api_key:
                        codes = await self.extract_with_openai(image_data)
                elif preferred_method == "gemini" and self.gemini_api_key:
                    codes = await self.extract_with_gemini(image_data, mime_type)
                elif preferred_method == "openai" and self.openai_api_key:
                    codes = await self.extract_with_openai(image_data)
                
                # Save to cache regardless of whether codes were found
                self._save_to_cache(image_hash, codes)
                
                if codes:
                    for code in codes:
                        extracted_codes.append({
                            'code': code,
                            'source': 'ocr',
                            'method': preferred_method,
                            'image_url': image_url,
                            'image_alt': image_info.get('alt', ''),
                            'confidence': 'medium'  # OCR confidence is generally medium
                        })
                    logger.info(f"Extracted {len(codes)} codes from image: {codes}")
                else:
                    logger.info(f"No codes found in image {i+1}")
                    
            except Exception as e:
                logger.warning(f"Error processing image {i+1}: {e}")
                
        return extracted_codes

    def get_setup_instructions(self) -> Dict[str, str]:
        """Get setup instructions for OCR configuration"""
        return {
            "gemini": """
To use Google Gemini for OCR:
1. Go to https://aistudio.google.com/app/apikey
2. Create a new API key
3. Add to your .env file: GEMINI_API_KEY="your_api_key_here"
4. Gemini offers generous free tier (15 requests per minute)

Cost: Free tier available, then ~$0.0025 per image
""",
            "openai": """
To use OpenAI Vision for OCR:
1. Go to https://platform.openai.com/api-keys
2. Create a new API key
3. Add to your .env file: OPENAI_API_KEY="your_api_key_here"
4. Requires paid account with credits

Cost: ~$0.003 per image (gpt-4o-mini model)
""",
            "github": """
To use GitHub Issues as fallback:
1. Go to https://github.com/settings/tokens
2. Create a personal access token with 'repo' scope
3. Add to your .env file: 
   GITHUB_TOKEN="your_token_here"
   REPO_OWNER="your_username"
   REPO_NAME="always-attend"

This will create issues with image links for manual processing.
"""
        }
