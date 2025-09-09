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
        """Detect only attendance code images in Gmail emails.

        Rules:
        - Accept images proxied via ci*.googleusercontent.com/meips/... that include
          an original URL after '#' pointing to learning.monash.edu tokenpluginfile .png
        - Also accept direct anchors to learning.monash.edu tokenpluginfile PNGs
        - Exclude gstatic icons, logos, and small UI images entirely
        """
        images: List[Dict[str, str]] = []

        def is_google_meips_with_learning(url: str) -> Optional[str]:
            # Expect pattern: https://ci3.googleusercontent.com/meips/...#https://learning.monash.edu/.../image.png
            if not url:
                return None
            low = url.lower()
            if 'googleusercontent.com/meips/' in low and '#http' in low:
                try:
                    original = url.split('#', 1)[1]
                except Exception:
                    return None
                original = self._fix_learning_monash_url(original)
                if original.startswith('https://learning.monash.edu/') and original.lower().endswith('.png'):
                    return original
            return None

        try:
            # Limit search to the email body area to avoid UI icons
            body_root = page.locator('div.a3s, .ii.gt').first

            # 1) IMG tags that are Google proxy with original after '#'
            try:
                img_elements = body_root.locator('img[src*="googleusercontent.com/meips/"]')
                n = await img_elements.count()
                for i in range(n):
                    src = await img_elements.nth(i).get_attribute('src')
                    alt = await img_elements.nth(i).get_attribute('alt') or ''
                    original = is_google_meips_with_learning(src or '')
                    if original:
                        images.append({'src': original, 'original_src': src or '', 'alt': alt})
            except Exception:
                pass

            # 2) Anchor tags linking directly to learning.monash.edu tokenpluginfile PNGs
            try:
                anchors = body_root.locator('a[href*="learning.monash.edu"][href*="tokenpluginfile.php"][href$=".png"]')
                m = await anchors.count()
                for i in range(m):
                    href = await anchors.nth(i).get_attribute('href')
                    if not href:
                        continue
                    fixed = self._fix_learning_monash_url(href)
                    if fixed.lower().endswith('.png'):
                        images.append({'src': fixed, 'original_src': href, 'alt': ''})
            except Exception:
                pass

        except Exception as e:
            logger.warning(f"Error detecting images in Gmail: {e}")

        # Deduplicate by src
        seen = set()
        uniq: List[Dict[str, str]] = []
        for it in images:
            key = it.get('src')
            if key and key not in seen:
                seen.add(key)
                uniq.append(it)

        logger.info(f"Found {len(uniq)} potential attendance code images")
        return uniq

    def _fix_learning_monash_url(self, url: str) -> str:
        """Fix soft-wrap artifacts in learning.monash.edu URLs (remove '=' and newlines).

        Only apply aggressive cleanup for learning.monash.edu URLs.
        """
        if "learning.monash.edu" in url:
            fixed = url.replace("\n", "").replace("\r", "")
            # Remove soft-wrap '=' characters common in quoted-printable emails
            fixed = fixed.replace("=", "")
            # Unescape any stray whitespace encodings if present
            fixed = fixed.replace("\t", "")
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

    async def download_and_rename_image(self, image_info: Dict[str, Any], course_code: str = None, week_number: str = None, page: Page = None) -> Optional[str]:
        """Download image and save it with a proper filename for OCR processing"""
        try:
            src = image_info.get('download_url') or image_info.get('src')
            logger.info(f"Downloading image: {src}")
            
            # Download the image
            result = await self.download_image(src, page=page)
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

    async def download_image(self, image_url: str, page: Page = None) -> Optional[Tuple[bytes, str]]:
        """Download image from URL and return bytes with mime type
        
        Args:
            image_url: URL of the image to download
            page: Optional authenticated Playwright page to use for download
        """
        try:
            # For learning.monash.edu URLs, use wget directly to avoid SSL certificate issues
            if 'learning.monash.edu' in image_url:
                logger.info(f"[WGET] Using wget directly for learning.monash.edu: {image_url[:80]}...")
                external_result = await self._download_with_external_tool(image_url)
                if external_result:
                    return external_result
                logger.warning(f"[WGET] External tool failed, falling back to other methods")
            
            # If we have an authenticated page, use it for download (for non-learning.monash.edu URLs)
            if page is not None and 'learning.monash.edu' not in image_url:
                try:
                    logger.debug(f"[AUTH DOWNLOAD] Attempting authenticated download: {image_url}")
                    
                    response = await page.request.get(image_url)
                    
                    if response.status == 200:
                        image_data = await response.body()
                        content_type = response.headers.get('content-type', 'image/jpeg')
                        
                        # Validate image size (limit to 20MB)
                        if len(image_data) > 20 * 1024 * 1024:
                            logger.warning(f"Image too large: {len(image_data)} bytes")
                            return None
                        
                        # Validate minimum size (at least 1KB)
                        if len(image_data) < 1024:
                            logger.warning(f"Image too small: {len(image_data)} bytes")
                            return None
                            
                        logger.info(f"[AUTH DOWNLOAD] Success! Downloaded {len(image_data)} bytes, type: {content_type}")
                        return image_data, content_type
                    else:
                        logger.warning(f"[AUTH DOWNLOAD] HTTP {response.status} when downloading image via page: {image_url}")
                        
                except Exception as e:
                    logger.debug(f"[AUTH DOWNLOAD] Page-based download failed: {e}")
                    # Fall through to aiohttp method
            
            # Fallback to aiohttp (for backwards compatibility or when page not available)
            logger.debug(f"Using aiohttp to download: {image_url}")
            
            # Configure headers with realistic User-Agent (user specifically requested this)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Sec-Fetch-Dest': 'image',
                'Sec-Fetch-Mode': 'no-cors',
                'Sec-Fetch-Site': 'cross-site',
                'Referer': 'https://learning.monash.edu/',  # Add referer for Monash images
                'Cache-Control': 'no-cache'
            }
            
            # Configure SSL settings - bypass SSL verification for learning.monash.edu
            import ssl
            ssl_context = ssl.create_default_context()
            
            # For learning.monash.edu URLs, disable SSL verification due to self-signed certificates
            if 'learning.monash.edu' in image_url:
                logger.debug(f"[SSL BYPASS] Disabling SSL verification for learning.monash.edu: {image_url}")
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            else:
                # For other URLs, use standard SSL verification
                logger.debug(f"[SSL STANDARD] Using standard SSL verification: {image_url}")
            
            # Configure connector with SSL context and timeout
            connector = aiohttp.TCPConnector(
                ssl=ssl_context,
                ttl_dns_cache=300,
                use_dns_cache=True,
                limit=10,
                limit_per_host=5
            )
            
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            
            async with aiohttp.ClientSession(
                connector=connector, 
                timeout=timeout, 
                headers=headers
            ) as session:
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
                            
                        logger.info(f"[AIOHTTP SUCCESS] Downloaded {len(image_data)} bytes, type: {content_type} from {image_url}")
                        return image_data, content_type
                    else:
                        logger.warning(f"HTTP {response.status} when downloading image: {image_url}")
                        return None
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Failed to download image {image_url}: {e}")
            
            # Final fallback: try external tool for learning.monash.edu URLs or SSL errors
            if 'learning.monash.edu' in image_url or 'ssl' in error_msg.lower() or 'certificate' in error_msg.lower():
                logger.info(f"[EXTERNAL FALLBACK] Trying external tool as final fallback for {image_url}")
                external_result = await self._download_with_external_tool(image_url)
                if external_result:
                    return external_result
                    
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
                                      preferred_method: str = "auto", page: Page = None) -> List[Dict[str, Any]]:
        """Extract attendance codes from a list of images with AI recommendations"""
        extracted_codes = []
        
        # Clean up old cache files at the start
        self._cleanup_old_cache()
        
        # Show AI method recommendation to user if images detected
        if images and self._should_recommend_ai():
            self._prompt_ai_recommendation(len(images))
        
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
                download_result = await self.download_image(image_url, page=page)
                if not download_result:
                    continue
                
                image_data, mime_type = download_result
                codes = []
                
                # Enhanced AI method processing with direct data handling
                codes = await self._process_image_with_ai(image_data, mime_type, preferred_method, image_url)
                
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
    def _should_recommend_ai(self) -> bool:
        """Check if AI methods should be recommended to user"""
        has_ai_key = bool(self.gemini_api_key or self.openai_api_key)
        return has_ai_key
    
    def _prompt_ai_recommendation(self, image_count: int) -> None:
        """Prompt user about AI method recommendation"""
        if self.gemini_api_key and self.openai_api_key:
            logger.info(f"📸 Found {image_count} attendance code images")
            logger.info("🤖 AI RECOMMENDED: Both Gemini and OpenAI are available for high-accuracy OCR")
            logger.info("💡 Tip: Gemini offers free tier (15 requests/min), OpenAI requires credits (~$0.003/image)")
        elif self.gemini_api_key:
            logger.info(f"📸 Found {image_count} attendance code images")
            logger.info("🤖 AI RECOMMENDED: Google Gemini is configured for high-accuracy OCR")
            logger.info("💡 Tip: Gemini offers generous free tier (15 requests/min)")
        elif self.openai_api_key:
            logger.info(f"📸 Found {image_count} attendance code images")
            logger.info("🤖 AI RECOMMENDED: OpenAI Vision is configured for high-accuracy OCR")
            logger.info("💡 Tip: OpenAI costs ~$0.003 per image but offers excellent accuracy")
        else:
            logger.info(f"📸 Found {image_count} attendance code images")
            logger.info("🤖 AI RECOMMENDED: Configure Gemini (free tier) or OpenAI for better accuracy")
            logger.info("💡 Tip: Run setup wizard or see OCR configuration instructions")
    
    async def _process_image_with_ai(self, image_data: bytes, mime_type: str, 
                                   preferred_method: str, image_url: str) -> List[str]:
        """Process image with AI methods and direct data handling"""
        codes = []
        
        try:
            if preferred_method == "auto":
                # Smart auto-selection: prefer Gemini for free tier, OpenAI for accuracy
                if self.gemini_api_key:
                    logger.info("🤖 Using Gemini AI for direct image processing...")
                    codes = await self.extract_with_gemini(image_data, mime_type)
                    if codes:
                        logger.info(f"✨ Gemini extracted {len(codes)} codes: {codes}")
                elif self.openai_api_key:
                    logger.info("🤖 Using OpenAI Vision for direct image processing...")
                    codes = await self.extract_with_openai(image_data)
                    if codes:
                        logger.info(f"✨ OpenAI extracted {len(codes)} codes: {codes}")
                else:
                    logger.warning("⚠️  No AI methods configured - consider setting up Gemini or OpenAI")
            elif preferred_method == "gemini" and self.gemini_api_key:
                logger.info("🤖 Processing with Gemini AI (user preference)...")
                codes = await self.extract_with_gemini(image_data, mime_type)
            elif preferred_method == "openai" and self.openai_api_key:
                logger.info("🤖 Processing with OpenAI Vision (user preference)...")
                codes = await self.extract_with_openai(image_data)
            else:
                logger.warning(f"⚠️  Requested method '{preferred_method}' not available or not configured")
                
        except Exception as e:
            logger.warning(f"🚨 AI processing failed for {image_url[:50]}...: {e}")
            
        return codes
    
    async def _download_with_external_tool(self, image_url: str) -> Optional[Tuple[bytes, str]]:
        """Download image using external tools (wget/curl) as fallback for SSL issues"""
        try:
            import subprocess
            import platform
            
            logger.debug(f"[EXTERNAL] Attempting external tool download: {image_url}")
            
            # Create temporary file path
            temp_dir = tempfile.gettempdir()
            temp_file = os.path.join(temp_dir, f"always_attend_img_{hashlib.md5(image_url.encode()).hexdigest()[:8]}")
            
            # Try wget first (more reliable for SSL issues)
            wget_success = False
            if platform.system() != "Windows":  # wget usually available on Unix systems
                try:
                    cmd = [
                        'wget', 
                        '--no-check-certificate',  # Bypass SSL verification
                        '--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        '--timeout=30',
                        '--tries=3',
                        '-O', temp_file,
                        image_url
                    ]
                    
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
                    if result.returncode == 0 and os.path.exists(temp_file) and os.path.getsize(temp_file) > 0:
                        logger.info(f"[EXTERNAL] wget successfully downloaded image: {os.path.getsize(temp_file)} bytes")
                        wget_success = True
                    else:
                        logger.debug(f"[EXTERNAL] wget failed: return code {result.returncode}, stderr: {result.stderr}")
                        
                except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                    logger.debug(f"[EXTERNAL] wget not available or timeout: {e}")
            
            # Try curl as fallback
            curl_success = False
            if not wget_success:
                try:
                    cmd = [
                        'curl',
                        '-k',  # Ignore SSL certificate errors
                        '--user-agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        '--connect-timeout', '30',
                        '--max-time', '45',
                        '--retry', '3',
                        '--retry-delay', '1',
                        '--location',  # Follow redirects
                        '--output', temp_file,
                        image_url
                    ]
                    
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    if result.returncode == 0 and os.path.exists(temp_file) and os.path.getsize(temp_file) > 0:
                        logger.info(f"[EXTERNAL] curl successfully downloaded image: {os.path.getsize(temp_file)} bytes")
                        curl_success = True
                    else:
                        logger.debug(f"[EXTERNAL] curl failed: return code {result.returncode}, stderr: {result.stderr}")
                        
                except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                    logger.debug(f"[EXTERNAL] curl not available or timeout: {e}")
            
            # Read the downloaded file
            if wget_success or curl_success:
                try:
                    with open(temp_file, 'rb') as f:
                        image_data = f.read()
                    
                    # Clean up temp file
                    try:
                        os.remove(temp_file)
                    except Exception:
                        pass
                    
                    # Validate image size
                    if len(image_data) > 20 * 1024 * 1024:
                        logger.warning(f"[EXTERNAL] Image too large: {len(image_data)} bytes")
                        return None
                    
                    if len(image_data) < 1024:
                        logger.warning(f"[EXTERNAL] Image too small: {len(image_data)} bytes")
                        return None
                    
                    # Determine content type from URL extension
                    content_type = 'image/jpeg'  # Default
                    if image_url.lower().endswith('.png'):
                        content_type = 'image/png'
                    elif image_url.lower().endswith('.gif'):
                        content_type = 'image/gif'
                    elif image_url.lower().endswith('.webp'):
                        content_type = 'image/webp'
                    
                    logger.info(f"[EXTERNAL] Successfully downloaded {len(image_data)} bytes, type: {content_type}")
                    return image_data, content_type
                    
                except Exception as e:
                    logger.warning(f"[EXTERNAL] Error reading downloaded file: {e}")
                    # Clean up temp file on error
                    try:
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                    except Exception:
                        pass
            else:
                logger.warning(f"[EXTERNAL] All external tools failed to download: {image_url}")
            
        except Exception as e:
            logger.warning(f"[EXTERNAL] External tool download failed: {e}")
        
        return None

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
