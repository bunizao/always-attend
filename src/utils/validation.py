#!/usr/bin/env python3
"""
 █████╗ ██╗     ██╗    ██╗ █████╗ ██╗   ██╗███████╗
██╔══██╗██║     ██║    ██║██╔══██╗╚██╗ ██╔╝██╔════╝
███████║██║     ██║ █╗ ██║███████║ ╚████╔╝ ███████╗
██╔══██║██║     ██║███╗██║██╔══██║  ╚██╔╝  ╚════██║
██║  ██║███████╗╚███╔███╔╝██║  ██║   ██║   ███████║
╚═╝  ╚═╝╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝

 █████╗ ████████╗████████╗███████╗███╗   ██╗██████╗ 
██╔══██╗╚══██╔══╝╚══██╔══╝██╔════╝████╗  ██║██╔══██╗
███████║   ██║      ██║   █████╗  ██╔██╗ ██║██║  ██║
██╔══██║   ██║      ██║   ██╔══╝  ██║╚██╗██║██║  ██║
██║  ██║   ██║      ██║   ███████╗██║ ╚████║██████╔╝
╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚══════╝╚═╝  ╚═══╝╚═════╝ 
src/utils/validation.py
Validation helpers for user inputs in Always Attend.

Provides comprehensive validation for user inputs and configurations
"""

import os
import re
import json
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse
from pathlib import Path

from always_attend.paths import env_file as default_env_file

def validate_email(email: str) -> Tuple[bool, str]:
    """
    Validate email address format with detailed feedback.
    
    Args:
        email: Email address to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not email or not email.strip():
        return False, "邮箱地址不能为空"
    
    email = email.strip()
    
    # Basic format check
    if '@' not in email:
        return False, "邮箱地址必须包含 @ 符号"
    
    if email.count('@') != 1:
        return False, "邮箱地址只能包含一个 @ 符号"
    
    # Split into local and domain parts
    local, domain = email.split('@', 1)
    
    if not local:
        return False, "@ 符号前必须有用户名部分"
    
    if not domain:
        return False, "@ 符号后必须有域名部分"
    
    # Check for spaces (common user mistake)
    if ' ' in email:
        return False, "邮箱地址不能包含空格"
    
    # Check local part
    if len(local) > 64:
        return False, "用户名部分过长（最多64个字符）"
    
    # Check domain part
    if len(domain) > 255:
        return False, "域名部分过长（最多255个字符）"
    
    if not re.match(r'^[a-zA-Z0-9.-]+$', domain):
        return False, "域名包含无效字符"
    
    if domain.startswith('.') or domain.endswith('.'):
        return False, "域名不能以点号开始或结束"
    
    if '..' in domain:
        return False, "域名不能包含连续的点号"
    
    # Check for educational domain (preferred but not required)
    educational_domains = ['.edu', '.edu.au', '.edu.my', '.ac.', '.edu.cn', '.edu.hk']
    is_educational = any(domain.lower().endswith(edu_domain) for edu_domain in educational_domains)
    
    # Basic regex validation
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return False, "邮箱地址格式不正确"
    
    # Additional warnings for non-educational emails
    if not is_educational:
        return True, f"⚠️ 建议使用学校邮箱（通常以 .edu 结尾），当前邮箱：{email}"
    
    return True, f"✅ 邮箱地址格式正确：{email}"

def validate_url(url: str, url_type: str = "URL") -> Tuple[bool, str]:
    """
    Validate URL format.
    
    Args:
        url: URL to validate
        url_type: Type of URL for error messages
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not url or not url.strip():
        return False, f"{url_type} 不能为空"
    
    url = url.strip()
    
    try:
        parsed = urlparse(url)
        
        if not parsed.scheme:
            return False, f"{url_type} 必须包含协议（如 https://）"
        
        if parsed.scheme not in ['http', 'https']:
            return False, f"{url_type} 必须使用 http 或 https 协议"
        
        if not parsed.netloc:
            return False, f"{url_type} 必须包含有效的域名"
        
        # Check for common mistakes
        if ' ' in url:
            return False, f"{url_type} 不能包含空格"
        
        if url.endswith('/login') or url.endswith('/signin'):
            return True, f"⚠️ {url_type} 似乎指向登录页面，请确认这是正确的入口地址"
        
        return True, f"✅ {url_type} 格式正确"
        
    except Exception as e:
        return False, f"{url_type} 格式无效：{str(e)}"

def validate_totp_secret(secret: str) -> Tuple[bool, str]:
    """
    Validate TOTP secret format.
    
    Args:
        secret: TOTP secret to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not secret or not secret.strip():
        return False, "TOTP 密钥不能为空"
    
    secret = secret.strip()
    
    # Remove common formatting (spaces, dashes)
    clean_secret = secret.replace(' ', '').replace('-', '').upper()
    
    # Check if it's valid Base32
    base32_pattern = r'^[A-Z2-7]+=*$'
    if not re.match(base32_pattern, clean_secret):
        return False, "TOTP 密钥必须是有效的 Base32 格式（A-Z, 2-7）"
    
    # Check length (common lengths are 16, 26, 32 characters)
    if len(clean_secret) < 16:
        return False, f"TOTP 密钥太短（{len(clean_secret)} 字符），至少需要 16 字符"
    
    if len(clean_secret) > 128:
        return False, f"TOTP 密钥太长（{len(clean_secret)} 字符），最多 128 字符"
    
    # Test if we can generate a code
    try:
        import pyotp
        totp = pyotp.TOTP(clean_secret)
        test_code = totp.now()
        if len(test_code) == 6 and test_code.isdigit():
            return True, "✅ TOTP 密钥格式正确"
        else:
            return False, "TOTP 密钥无法生成有效的验证码"
    except Exception as e:
        return False, f"TOTP 密钥验证失败：{str(e)}"

def validate_credentials(username: str, password: str) -> List[str]:
    """
    Validate username and password with helpful feedback.
    
    Args:
        username: Username to validate
        password: Password to validate
        
    Returns:
        List of validation messages (warnings and errors)
    """
    messages = []
    
    # Username validation
    if not username or not username.strip():
        messages.append("❌ 用户名不能为空")
    else:
        username = username.strip()
        if len(username) < 3:
            messages.append("⚠️ 用户名可能过短，通常学号至少3位数")
        if ' ' in username:
            messages.append("⚠️ 用户名包含空格，请确认是否正确")
        if not re.match(r'^[a-zA-Z0-9._@-]+$', username):
            messages.append("⚠️ 用户名包含特殊字符，请确认是否正确")
    
    # Password validation
    if not password:
        messages.append("❌ 密码不能为空")
    else:
        if len(password) < 6:
            messages.append("⚠️ 密码可能过短，建议至少6位")
        if password.isdigit():
            messages.append("⚠️ 纯数字密码安全性较低")
        if password.lower() == password:
            messages.append("⚠️ 建议密码包含大写字母")
    
    if not messages:
        messages.append("✅ 用户名和密码格式检查通过")
    
    return messages

def validate_env_file(env_path: str = str(default_env_file())) -> List[str]:
    """
    Comprehensive validation of .env file.
    
    Args:
        env_path: Path to .env file
        
    Returns:
        List of validation messages
    """
    messages = []
    
    if not os.path.exists(env_path):
        messages.append("❌ .env 配置文件不存在")
        return messages
    
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        messages.append(f"❌ 无法读取 .env 文件：{e}")
        return messages
    
    if not content.strip():
        messages.append("❌ .env 文件为空")
        return messages
    
    # Parse environment variables
    env_vars = {}
    for line_num, line in enumerate(content.split('\n'), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        if '=' not in line:
            messages.append(f"⚠️ 第{line_num}行格式错误：{line}")
            continue
        
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        env_vars[key] = value
    
    # Check required variables
    required_vars = ['USERNAME', 'PASSWORD', 'PORTAL_URL']
    for var in required_vars:
        if var not in env_vars or not env_vars[var]:
            messages.append(f"❌ 缺少必需配置：{var}")
    
    # Validate specific configurations
    if 'USERNAME' in env_vars and env_vars['USERNAME']:
        cred_messages = validate_credentials(env_vars['USERNAME'], env_vars.get('PASSWORD', ''))
        messages.extend(cred_messages)
    
    if 'PORTAL_URL' in env_vars and env_vars['PORTAL_URL']:
        is_valid, msg = validate_url(env_vars['PORTAL_URL'], "考勤系统网址")
        messages.append(msg)
    
    if 'TOTP_SECRET' in env_vars and env_vars['TOTP_SECRET']:
        is_valid, msg = validate_totp_secret(env_vars['TOTP_SECRET'])
        messages.append(msg)
    
    if 'SCHOOL_EMAIL' in env_vars and env_vars['SCHOOL_EMAIL']:
        is_valid, msg = validate_email(env_vars['SCHOOL_EMAIL'])
        messages.append(msg)
    
    # Check for common mistakes
    if 'HEADLESS' in env_vars:
        headless_val = env_vars['HEADLESS'].lower()
        if headless_val not in ['0', '1', 'true', 'false']:
            messages.append("⚠️ HEADLESS 值建议使用 0, 1, true, 或 false")
    
    return messages

def validate_data_files() -> List[str]:
    """
    Validate data directory structure and JSON files.
    
    Returns:
        List of validation messages
    """
    messages = []
    data_dir = Path('data')
    
    if not data_dir.exists():
        messages.append("ℹ️ data 目录不存在，将使用其他方式获取考勤代码")
        return messages
    
    course_dirs = [d for d in data_dir.iterdir() if d.is_dir()]
    if not course_dirs:
        messages.append("ℹ️ data 目录为空，将使用其他方式获取考勤代码")
        return messages
    
    for course_dir in course_dirs:
        course_name = course_dir.name
        json_files = list(course_dir.glob('*.json'))
        
        if not json_files:
            messages.append(f"⚠️ 课程 {course_name} 没有数据文件")
            continue
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if not isinstance(data, list):
                    messages.append(f"⚠️ {json_file} 格式错误：应该是数组格式")
                    continue
                
                for i, item in enumerate(data):
                    if not isinstance(item, dict):
                        messages.append(f"⚠️ {json_file} 第{i+1}项格式错误：应该是对象格式")
                        continue
                    
                    if 'code' not in item or not item['code']:
                        messages.append(f"⚠️ {json_file} 第{i+1}项缺少 code 字段")
                    
                    if 'slot' not in item:
                        messages.append(f"⚠️ {json_file} 第{i+1}项缺少 slot 字段")
                
            except json.JSONDecodeError as e:
                messages.append(f"❌ {json_file} JSON 格式错误：{e}")
            except Exception as e:
                messages.append(f"❌ 无法读取 {json_file}：{e}")
    
    if not any("❌" in msg for msg in messages[-10:]):  # Check last 10 messages
        messages.append("✅ 数据文件格式检查通过")
    
    return messages

def comprehensive_validation() -> None:
    """
    Run comprehensive validation of the entire setup.
    """
    print("🔍 开始全面配置验证...")
    print("=" * 50)
    
    all_messages = []
    
    # Validate .env file
    print("📝 检查配置文件...")
    env_messages = validate_env_file()
    all_messages.extend(env_messages)
    for msg in env_messages:
        print(f"  {msg}")
    
    print("\n📂 检查数据文件...")
    data_messages = validate_data_files()
    all_messages.extend(data_messages)
    for msg in data_messages:
        print(f"  {msg}")
    
    print("\n" + "=" * 50)
    
    # Summary
    errors = len([msg for msg in all_messages if msg.startswith("❌")])
    warnings = len([msg for msg in all_messages if msg.startswith("⚠️")])
    success = len([msg for msg in all_messages if msg.startswith("✅")])
    
    print(f"📊 验证结果：{success} 项通过，{warnings} 项警告，{errors} 项错误")
    
    if errors == 0:
        print("🎉 配置验证完成，可以开始使用！")
    else:
        print("⚠️ 发现配置问题，请根据上述提示进行修正")

if __name__ == "__main__":
    comprehensive_validation()
