import os
import subprocess
import argparse
import logging
from bs4 import BeautifulSoup
import re
from urllib.parse import urlparse
import requests
from requests.exceptions import RequestException
import shutil

# Configure logging to capture detailed debug information
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG to capture all levels of logs
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("markdown_conversion.log"),
        logging.StreamHandler()
    ]
)

def sanitize_file_path(file_path):
    """
    Sanitize the file path by removing newlines and trimming whitespace.

    Args:
        file_path (str): The original file path.

    Returns:
        str: The sanitized file path.
    """
    sanitized = os.path.normpath(file_path.strip().replace('\n', ''))
    logging.debug(f"Sanitized file path: Original='{file_path}' | Sanitized='{sanitized}'")
    return sanitized


def slugify(text):
    """
    Create a slug from heading text by stripping non-alphanumeric, lowercasing, replacing spaces with hyphens.
    """
    slug = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s]+", "-", slug)

class MarkdownToHtmlConverter:
    """
    A class to convert Markdown files to HTML with custom styling using a predefined CSS stylesheet,
    and to generate an HTML Table of Contents from the Markdown headings.
    """
    # Constants
    STYLE_CSS_FILENAME = 'markdown-styles-v1.8.1-cn_final.css'
    STYLE_CSS_URL = 'https://docs.oasis-open.org/templates/css/markdown-styles-v1.8.1-cn_final.css'
    LOGO_IMG_TAG = '<img alt="OASIS Logo" src="https://docs.oasis-open.org/templates/OASISLogo-v3.0.png"/>'
    IMAGES_SUBDIR = 'images'

    def __init__(self, md_file, output_file, git_repo_basedir=None, md_dir=None, styles_dir='styles'):
        # Sanitize and store file paths
        self.md_file = sanitize_file_path(md_file)
        self.output_file = sanitize_file_path(output_file)
        self.git_repo_basedir = sanitize_file_path(git_repo_basedir) if git_repo_basedir else None
        self.md_dir = sanitize_file_path(md_dir) if md_dir else None
        self.styles_dir = sanitize_file_path(styles_dir)

        logging.info("Initialized MarkdownToHtmlConverter with:")
        logging.info(f"  Markdown File: {self.md_file}")
        logging.info(f"  Output File: {self.output_file}")
        logging.info(f"  Git Repo Base Dir: {self.git_repo_basedir}")
        logging.info(f"  Markdown Directory: {self.md_dir}")
        logging.info(f"  Styles Directory: {self.styles_dir}")

        # Extract metadata
        self.meta_description = self.extract_meta_description()
        self.html_title = self.extract_html_title()

        # Prepare directories
        self.images_dir = os.path.join(os.path.dirname(self.output_file), self.IMAGES_SUBDIR)
        os.makedirs(self.images_dir, exist_ok=True)
        logging.debug(f"Images directory ensured at: {self.images_dir}")

        self.styles_path = os.path.join(os.path.dirname(self.output_file), self.styles_dir)
        os.makedirs(self.styles_path, exist_ok=True)
        logging.debug(f"Styles directory ensured at: {self.styles_path}")

        # Ensure CSS present
        self.ensure_stylesheet()

    def ensure_stylesheet(self):
        style_css_path = os.path.join(self.styles_path, self.STYLE_CSS_FILENAME)
        if not os.path.exists(style_css_path):
            logging.warning(f"Style CSS file not found at {style_css_path}. Downloading...")
            self.download_stylesheet(style_css_path)
        else:
            logging.info(f"Stylesheet already exists at {style_css_path}.")

    def download_stylesheet(self, destination_path):
        logging.info(f"Downloading stylesheet from {self.STYLE_CSS_URL} to {destination_path}.")
        try:
            response = requests.get(self.STYLE_CSS_URL, timeout=10)
            response.raise_for_status()
            with open(destination_path, 'wb') as f:
                f.write(response.content)
            logging.info("Stylesheet downloaded successfully.")
        except RequestException as e:
            logging.error(f"Failed to download stylesheet: {e}")
            raise

    def extract_meta_description(self):
        logging.info("Extracting meta description from markdown file.")
        try:
            with open(self.md_file, 'r', encoding='utf-8') as file:
                for line in file:
                    if line.startswith('<!--') and 'description:' in line:
                        match = re.search(r'description:\s*(.*?)\s*-->', line)
                        if match:
                            desc = match.group(1).strip()
                            logging.info(f"Meta description: {desc}")
                            return desc
            logging.warning("No meta description found.")
            return '-'
        except Exception as e:
            logging.error(f"Error extracting meta description: {e}")
            return '-'

    def extract_html_title(self):
        logging.info("Extracting HTML title from markdown file.")
        try:
            with open(self.md_file, 'r', encoding='utf-8') as file:
                for line in file:
                    if line.startswith('# '):
                        title = line.lstrip('# ').strip()
                        logging.info(f"HTML title: {title}")
                        return title
            logging.warning("No HTML title found.")
            return '-'
        except Exception as e:
            logging.error(f"Error extracting HTML title: {e}")
            return '-'

    def run_pandoc(self):
        logging.info("Running Pandoc conversion.")
        style_css_path = os.path.abspath(os.path.join(self.styles_path, self.STYLE_CSS_FILENAME))
        temp_html = os.path.join(os.path.dirname(self.output_file), 'temp_output.html')
        cmd = [
            'pandoc', self.md_file,
            '-f', 'markdown+autolink_bare_uris+hard_line_breaks',
            '-c', style_css_path,
            '-s', '-o', temp_html,
            '--metadata', f'title={self.html_title}'
        ]
        logging.debug('Pandoc CMD: ' + ' '.join(cmd))
        subprocess.run(cmd, check=True)
        return temp_html

    def generate_html_toc(self, soup):
        logging.info("Generating HTML Table of Contents.")
        nav = BeautifulSoup('<nav id="table-of-contents"><h2>Table of Contents</h2><ul></ul></nav>', 'html.parser')
        ul = nav.ul
        for header in soup.find_all(re.compile('^h[1-4]$')):
            text = header.get_text().strip()
            if not header.get('id'):
                header['id'] = slugify(text)
            li = soup.new_tag('li')
            a = soup.new_tag('a', href=f"#{header['id']}")
            a.string = text
            li.append(a)
            ul.append(li)
        if soup.body:
            soup.body.insert(0, nav)
        return soup

    def post_process_html(self, html_content):
        logging.info("Post-processing HTML content.")
        soup = BeautifulSoup(html_content, 'html.parser')

        # Meta description
        if self.meta_description and self.meta_description != '-':
            tag = soup.new_tag('meta', attrs={'name':'description','content':self.meta_description})
            soup.head.insert(0, tag)

        # Convert URLs to links
        soup = BeautifulSoup(self.convert_urls_to_hyperlinks(str(soup)), 'html.parser')

        # Handle images
        for img in soup.find_all('img'):
            src = img.get('src','')
            if src == self.LOGO_IMG_TAG:
                img.decompose()
                continue
            parsed = urlparse(src)
            if parsed.scheme in ('http','https'):
                fname = os.path.basename(parsed.path)
                local = os.path.join(self.images_dir, fname)
                rel = os.path.join(self.IMAGES_SUBDIR, fname)
                if not os.path.exists(local):
                    try:
                        r = requests.get(src, timeout=10)
                        r.raise_for_status()
                        with open(local,'wb') as f: f.write(r.content)
                    except RequestException:
                        img.decompose()
                        continue
                img['src'] = rel

        # Insert logo
        logo = BeautifulSoup(self.LOGO_IMG_TAG, 'html.parser')
        if soup.body and not soup.body.find('img', {'src':re.compile('OASISLogo')}):
            soup.body.insert(0, logo)

        # Inject stylesheet link
        css_rel = os.path.relpath(os.path.join(self.styles_path, self.STYLE_CSS_FILENAME), os.path.dirname(self.output_file))
        link = soup.new_tag('link', rel='stylesheet', href=css_rel)
        soup.head.append(link)

        # Generate and insert TOC
        soup = self.generate_html_toc(soup)

        return str(soup)

    def convert_urls_to_hyperlinks(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        regex = re.compile(r'(https?://\S+)')
        for text in soup.find_all(string=regex):
            parts=[]; last=0
            for m in regex.finditer(text):
                parts.append(text[last:m.start()])
                a=soup.new_tag('a', href=m.group(1)); a.string=m.group(1)
                parts.append(a)
                last=m.end()
            parts.append(text[last:])
            for p in parts: text.insert_before(p)
            text.extract()
        return str(soup)

    def convert(self):
        temp = self.run_pandoc()
        html = self.read_file(temp)
        final = self.post_process_html(html)
        self.write_file(self.output_file, final)
        os.remove(temp)
        logging.info(f"Final HTML at {self.output_file}")

    def read_file(self, path):
        with open(path,'r',encoding='utf-8') as f: return f.read()

    def write_file(self, path, content):
        with open(path,'w',encoding='utf-8') as f: f.write(content)

def main():
    p=argparse.ArgumentParser(description='Enhanced MD->HTML with TOC')
    p.add_argument('md_file'); p.add_argument('output_file'); p.add_argument('--git_repo_basedir',default=None)
    args=p.parse_args()
    conv=MarkdownToHtmlConverter(args.md_file,args.output_file,args.git_repo_basedir)
    conv.convert()

if __name__=='__main__': main()
