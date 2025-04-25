#!/usr/bin/env python3

import os
import subprocess
import argparse
import logging
import re
from bs4 import BeautifulSoup
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
    generates a clickable HTML Table of Contents, and preserves full original functionality.
    """
    # Constants
    STYLE_CSS_FILENAME = 'markdown-styles-v1.8.1-cn_final.css'
    STYLE_CSS_URL = 'https://docs.oasis-open.org/templates/css/markdown-styles-v1.8.1-cn_final.css'
    LOGO_IMG_TAG = '<img alt="OASIS Logo" src="https://docs.oasis-open.org/templates/OASISLogo-v3.0.png"/>'
    IMAGES_SUBDIR = 'images'

    def __init__(self, md_file, output_file, git_repo_basedir=None, md_dir=None, styles_dir='styles'):
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

        self.meta_description = self.extract_meta_description()
        self.html_title = self.extract_html_title()

        # Prepare directories
        self.images_dir = os.path.join(os.path.dirname(self.output_file), self.IMAGES_SUBDIR)
        os.makedirs(self.images_dir, exist_ok=True)
        logging.debug(f"Images directory ensured at: {self.images_dir}")

        self.styles_path = os.path.join(os.path.dirname(self.output_file), self.styles_dir)
        os.makedirs(self.styles_path, exist_ok=True)
        logging.debug(f"Styles directory ensured at: {self.styles_path}")

        self.ensure_stylesheet()

    def ensure_stylesheet(self):
        style_css_path = os.path.join(self.styles_path, self.STYLE_CSS_FILENAME)
        if not os.path.exists(style_css_path):
            logging.warning(f"Style CSS file not found at {style_css_path}. Downloading...")
            self.download_stylesheet(style_css_path)
            self.commit_and_push(self.styles_path, style_css_path)
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

    def commit_and_push(self, styles_dir, file_path):
        logging.info("Committing and pushing the stylesheet to the repository.")
        try:
            subprocess.run(['git', 'config', '--global', 'user.name', 'Markdown Converter Bot'], check=True)
            subprocess.run(['git', 'config', '--global', 'user.email', 'converter-bot@example.com'], check=True)

            relative_path = os.path.relpath(file_path, self.git_repo_basedir)
            subprocess.run(['git', 'add', relative_path], cwd=self.git_repo_basedir, check=True)
            logging.debug(f"Staged file for commit: {relative_path}")

            commit_message = f"Add missing stylesheet: {self.STYLE_CSS_FILENAME}"
            subprocess.run(['git', 'commit', '-m', commit_message], cwd=self.git_repo_basedir, check=True)
            logging.info("Committed the stylesheet successfully.")

            subprocess.run(['git', 'push'], cwd=self.git_repo_basedir, check=True)
            logging.info("Pushed the commit to the repository successfully.")

        except subprocess.CalledProcessError as e:
            logging.error(f"Git command failed: {e}")
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

    def read_file(self, file_path):
        logging.debug(f"Reading file: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content

    def write_file(self, file_path, content):
        logging.debug(f"Writing to file: {file_path}")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

    def copy_local_images(self, source_images_dir):
        logging.info(f"Copying local images from {source_images_dir} to {self.images_dir}")
        if not os.path.exists(source_images_dir):
            logging.error(f"Source images directory does not exist: {source_images_dir}")
            return
        for img in os.listdir(source_images_dir):
            src = os.path.join(source_images_dir, img)
            dst = os.path.join(self.images_dir, img)
            try:
                shutil.copy(src, dst)
                logging.info(f"Copied {img} to {self.images_dir}")
            except Exception as e:
                logging.error(f"Failed to copy {img}: {e}")

    def run_pandoc(self):
        logging.info("Running Pandoc conversion.")
        style_css_path = os.path.abspath(os.path.join(self.styles_path, self.STYLE_CSS_FILENAME))
        temp_output = os.path.join(os.path.dirname(self.output_file), 'temp_output.html')
        cmd = [
            'pandoc', self.md_file,
            '-f', 'markdown+autolink_bare_uris+hard_line_breaks',
            '-c', style_css_path,
            '-s', '-o', temp_output,
            '--metadata', f'title={self.html_title}'
        ]
        logging.debug('Pandoc CMD: ' + ' '.join(cmd))
        subprocess.run(cmd, check=True)
        return temp_output

    def convert_urls_to_hyperlinks(self, html_content):
        logging.debug("Converting plain URLs to hyperlinks.")
        soup = BeautifulSoup(html_content, 'html.parser')
        url_regex = re.compile(r'(https?://\S+)')
        for text_node in soup.find_all(string=url_regex):
            new_content = []
            last = 0
            for m in url_regex.finditer(text_node):
                new_content.append(text_node[last:m.start()])
                a = soup.new_tag('a', href=m.group(1))
                a.string = m.group(1)
                new_content.append(a)
                last = m.end()
            new_content.append(text_node[last:])
            parent = text_node.parent
            for elem in new_content:
                parent.insert_before(elem)
            text_node.extract()
        return str(soup)

    def generate_html_toc(self, soup):
        logging.info("Generating HTML Table of Contents.")
        nav = BeautifulSoup('<nav id="table-of-contents"><h2>Table of Contents</h2><ul></ul></nav>', 'html.parser')
        ul = nav.ul
        for hdr in soup.find_all(re.compile('^h[1-4]$')):
            text = hdr.get_text().strip()
            if not hdr.get('id'):
                hdr['id'] = slugify(text)
            li = soup.new_tag('li')
            a = soup.new_tag('a', href=f"#{hdr['id']}")
            a.string = text
            li.append(a)
            ul.append(li)
        if soup.body:
            soup.body.insert(0, nav)
        return soup

    def post_process_html(self, html_content):
        logging.info("Post-processing HTML content.")
        soup = BeautifulSoup(html_content, 'html.parser')
        # Meta
        if self.meta_description != '-':
            m = soup.new_tag('meta', attrs={'name':'description','content':self.meta_description})
            soup.head.insert(0, m)
        # URLs
        soup = BeautifulSoup(self.convert_urls_to_hyperlinks(str(soup)), 'html.parser')
        # Images
        for img in soup.find_all('img'):
            src = img.get('src','')
            if src == "https://docs.oasis-open.org/templates/OASISLogo-v3.0.png":
                img.decompose(); continue
            parsed = urlparse(src)
            if parsed.scheme in ('http','https'):
                fname = os.path.basename(parsed.path)
                local = os.path.join(self.images_dir, fname)
                rel = os.path.join(self.IMAGES_SUBDIR, fname)
                if not os.path.exists(local):
                    try:
                        r = requests.get(src, timeout=10); r.raise_for_status()
                        with open(local,'wb') as f: f.write(r.content)
                    except RequestException:
                        img.decompose(); continue
                img['src'] = rel
        # Logo
        logo = BeautifulSoup(self.LOGO_IMG_TAG, 'html.parser')
        if soup.body and not soup.body.find('img', {'src':re.compile('OASISLogo')}):
            soup.body.insert(0, logo)
        # Stylesheet
        css_rel = os.path.relpath(os.path.join(self.styles_path, self.STYLE_CSS_FILENAME), os.path.dirname(self.output_file))
        lnk = soup.new_tag('link', rel='stylesheet', href=css_rel)
        soup.head.append(lnk)
        # TOC
        soup = self.generate_html_toc(soup)
        return str(soup)

    def ensure_toc_title(self):
        logging.info("Ensuring TOC title is present.")
        try:
            lines = open(self.md_file,'r',encoding='utf-8').readlines()
            toc_present = any(re.match(r'^- \[.*\]\(.*\)',ln) for ln in lines)
            title_present = any(re.match(r'^\s*#+\s*Table of Contents',ln,re.I) for ln in lines)
            if toc_present and not title_present:
                idx = next((i for i,ln in enumerate(lines) if re.match(r'^- \[.*\]\(.*\)',ln)),None)
                lvl = len(re.match(r'^(#+)',lines[0]).group(1))+1 if re.match(r'^(#+)',lines[0]) else 1
                heading = '#'*lvl + ' Table of Contents\n'
                lines.insert(idx, heading)
                open(self.md_file,'w',encoding='utf-8').writelines(lines)
        except Exception as e:
            logging.error(f"Error ensuring TOC title: {e}")

    def run_prettier(self):
        logging.info("Running Prettier for MD formatting.")
        cmd = ['prettier','--write',self.md_file]
        subprocess.run(cmd,check=True)

    def convert(self):
        temp = self.run_pandoc()
        html = self.read_file(temp)
        final = self.post_process_html(html)
        self.write_file(self.output_file, final)
        os.remove(temp)
        logging.info(f"Final HTML at {self.output_file}")


def main():
    parser = argparse.ArgumentParser(description='Markdown to HTML Converter with Custom Styling')
    parser.add_argument('md_file', help='Path to the Markdown file')
    parser.add_argument('git_repo_basedir', help='Base directory of git repository')
    parser.add_argument('md_dir', help='Directory containing the Markdown file')
    parser.add_argument('--test', action='store_true', help='Run in test mode')
    parser.add_argument('--md-format', action='store_true', help='Run Prettier to format the Markdown file')
    parser.add_argument('--md-to-html', action='store_true', help='Convert Markdown file to HTML')
    args = parser.parse_args()

    if args.test:
        repo = '/github/workspace'
        md_dir = repo
        md = os.path.join(md_dir, 'example.md')
        out = os.path.join(md_dir, 'example.html')
    else:
        repo = sanitize_file_path(args.git_repo_basedir)
        md_dir = sanitize_file_path(args.md_dir)
        md = sanitize_file_path(args.md_file)
        out = os.path.join(md_dir, os.path.basename(md).replace('.md','.html'))

    conv = MarkdownToHtmlConverter(md, out, repo, md_dir)
    if args.md_format:
        conv.run_prettier()
    if args.md_to_html:
        conv.convert()

if __name__ == '__main__':
    main()
