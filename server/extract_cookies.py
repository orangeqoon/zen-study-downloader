# -*- coding: utf-8 -*-
import os
import sys

DOMAINS = ["ed.nico", "nicovideo.jp", "dwango.jp"]

def to_netscape_string(c):
    domain = c.get('domain', '')
    flag = "TRUE" if domain.startswith('.') else "FALSE"
    path = c.get('path', '/')
    secure = "TRUE" if c.get('secure', False) else "FALSE"
    expires = c.get('expires')
    if expires is None:
        expires = 0
    else:
        try:
            expires = int(expires)
        except Exception:
            expires = 0
    name = c.get('name', '')
    value = c.get('value', '')
    return f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n"

def extract_cookies_to_file(out_path):
    try:
        import rookiepy
    except ImportError:
        print("[Cookie] rookiepy is not installed.")
        return False

    all_cookies = []
    browsers = [
        ("firefox", getattr(rookiepy, "firefox", None)),
        ("chrome", getattr(rookiepy, "chrome", None)),
        ("edge", getattr(rookiepy, "edge", None)),
        ("brave", getattr(rookiepy, "brave", None)),
        ("opera", getattr(rookiepy, "opera", None)),
        ("vivaldi", getattr(rookiepy, "vivaldi", None))
    ]

    for name, func in browsers:
        if func is None:
            continue
        try:
            cookies = func(DOMAINS)
            if cookies:
                all_cookies.extend(cookies)
        except Exception:
            pass

    if not all_cookies:
        return False

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# Generated automatically by ZEN Study Downloader\n\n")
            for c in all_cookies:
                f.write(to_netscape_string(c))
        return True
    except Exception as e:
        print(f"[Cookie] Error writing cookies file: {e}")
        return False

if __name__ == "__main__":
    app_dir = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(app_dir, "cookies_nico.txt")
    success = extract_cookies_to_file(out)
    if success:
        print(f"[Cookie] Successfully saved cookies to {out}")
    else:
        print("[Cookie] No cookies extracted.")
