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

class MarkdownToHtmlConverter:
    """
    A class to convert Markdown files to HTML with custom styling using a predefined CSS stylesheet.
    """

    # Constants
    STYLE_CSS_FILENAME = 'markdown-styles-v1.8.1-cn_final.css'
    STYLE_CSS_URL = 'https://docs.oasis-open.org/templates/css/markdown-styles-v1.8.1-cn_final.css'
    LOGO_IMG_TAG = '<img alt="OASIS Logo" src="https://docs.oasis-open.org/templates/OASISLogo-v3.0.png"/>'
    IMAGES_SUBDIR = 'images'

    def __init__(self, md_file, output_file, git_repo_basedir=None, md_dir=None, styles_dir='styles'):
        """
        Initializes the MarkdownToHtmlConverter with file paths and extracts metadata.

        Args:
            md_file (str): Path to the Markdown file.
            output_file (str): Path to the output HTML file.
            git_repo_basedir (str, optional): Base directory of the git repository.
            md_dir (str, optional): Directory containing the Markdown file.
            styles_dir (str, optional): Directory where stylesheets are stored.
        """
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

        # Extract metadata from the Markdown file
        self.meta_description = self.extract_meta_description()
        self.html_title = self.extract_html_title()

        # Ensure the images directory exists (relative to the HTML file)
        self.images_dir = os.path.join(os.path.dirname(self.output_file), self.IMAGES_SUBDIR)
        os.makedirs(self.images_dir, exist_ok=True)
        logging.debug(f"Images directory ensured at: {self.images_dir}")

        # Ensure the styles directory exists (relative to the output file)
        self.styles_path = os.path.join(os.path.dirname(self.output_file), self.styles_dir)
        os.makedirs(self.styles_path, exist_ok=True)
        logging.debug(f"Styles directory ensured at: {self.styles_path}")

        # Ensure the CSS file is present
        self.ensure_stylesheet()

    def ensure_stylesheet(self):
        """
        Ensures that the stylesheet is present in the styles directory.
        Downloads and commits it if it's missing.
        """
        style_css_path = os.path.join(self.styles_path, self.STYLE_CSS_FILENAME)
        if not os.path.exists(style_css_path):
            logging.warning(f"Style CSS file not found at {style_css_path}. Downloading...")
            try:
                self.download_stylesheet(style_css_path)
                self.commit_and_push(styles_dir=self.styles_path, file_path=style_css_path)
                logging.info(f"Downloaded and committed stylesheet to {style_css_path}.")
            except Exception as e:
                logging.error(f"Failed to download and commit stylesheet: {e}")
                raise
        else:
            logging.info(f"Stylesheet already exists at {style_css_path}.")

    def download_stylesheet(self, destination_path):
        """
        Downloads the stylesheet from the predefined URL.

        Args:
            destination_path (str): The path where the stylesheet will be saved.
        """
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
        """
        Commits and pushes the downloaded stylesheet to the git repository.

        Args:
            styles_dir (str): Directory where stylesheets are stored.
            file_path (str): Path to the stylesheet file.
        """
        logging.info("Committing and pushing the stylesheet to the repository.")
        try:
            # Configure Git if not already configured
            subprocess.run(['git', 'config', '--global', 'user.name', 'Markdown Converter Bot'], check=True)
            subprocess.run(['git', 'config', '--global', 'user.email', 'converter-bot@example.com'], check=True)

            # Stage the stylesheet
            relative_path = os.path.relpath(file_path, self.git_repo_basedir)
            subprocess.run(['git', 'add', relative_path], cwd=self.git_repo_basedir, check=True)
            logging.debug(f"Staged file for commit: {relative_path}")

            # Commit the stylesheet
            commit_message = f"Add missing stylesheet: {self.STYLE_CSS_FILENAME}"
            subprocess.run(['git', 'commit', '-m', commit_message], cwd=self.git_repo_basedir, check=True)
            logging.info("Committed the stylesheet successfully.")

            # Push the commit
            subprocess.run(['git', 'push'], cwd=self.git_repo_basedir, check=True)
            logging.info("Pushed the commit to the repository successfully.")

        except subprocess.CalledProcessError as e:
            logging.error(f"Git command failed: {e}")
            raise

    def extract_meta_description(self):
        """
        Extracts the meta description from the Markdown file.

        Returns:
            str: The extracted meta description or "-" if not found.
        """
        logging.info("Extracting meta description from markdown file.")
        try:
            with open(self.md_file, 'r', encoding='utf-8') as file:
                for line in file:
                    if line.startswith('<!--') and 'description:' in line:
                        # Extract the description content between 'description:' and '-->'
                        description_match = re.search(r'description:\s*(.*?)\s*-->', line)
                        if description_match:
                            desc = description_match.group(1).strip()
                            logging.info(f"Meta description extracted: {desc}")
                            return desc
            logging.warning("No meta description found in the markdown file.")
            return "-"
        except Exception as e:
            logging.error(f"Error extracting meta description: {e}")
            return "-"

    def extract_html_title(self):
        """
        Extracts the HTML title from the Markdown file.

        Returns:
            str: The extracted HTML title or "-" if not found.
        """
        logging.info("Extracting HTML title from markdown file.")
        try:
            with open(self.md_file, 'r', encoding='utf-8') as file:
                for line in file:
                    if line.startswith('# '):  # Assuming the title is the first H1 element
                        title = line.strip('# ').strip()
                        logging.info(f"HTML title extracted: {title}")
                        return title
            logging.warning("No HTML title found in the markdown file.")
            return "-"
        except Exception as e:
            logging.error(f"Error extracting HTML title: {e}")
            return "-"

    def read_file(self, file_path):
        """
        Reads the content of a file.

        Args:
            file_path (str): Path to the file.

        Returns:
            str: Content of the file.
        """
        logging.debug(f"Reading file: {file_path}")
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
            logging.debug(f"Read {len(content)} characters from {file_path}")
            return content
        except Exception as e:
            logging.error(f"Error reading file {file_path}: {e}")
            raise

    def write_file(self, file_path, content):
        """
        Writes content to a file.

        Args:
            file_path (str): Path to the file.
            content (str): Content to write.
        """
        logging.debug(f"Writing to file: {file_path}")
        try:
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(content)
            logging.debug(f"Wrote {len(content)} characters to {file_path}")
        except Exception as e:
            logging.error(f"Error writing to file {file_path}: {e}")
            raise

    def copy_local_images(self, source_images_dir):
        """
        Copies images from the source directory to the images/ directory.

        Args:
            source_images_dir (str): Path to the source images directory.
        """
        logging.info(f"Copying local images from {source_images_dir} to {self.images_dir}")
        if not os.path.exists(source_images_dir):
            logging.error(f"Source images directory does not exist: {source_images_dir}")
            return
        for image_name in os.listdir(source_images_dir):
            source_image_path = os.path.join(source_images_dir, image_name)
            destination_image_path = os.path.join(self.images_dir, image_name)
            try:
                shutil.copy(source_image_path, destination_image_path)
                logging.info(f"Copied {image_name} to {self.images_dir}")
            except Exception as e:
                logging.error(f"Failed to copy {image_name}: {e}")

    def run_pandoc(self):
        """
        Runs Pandoc to convert Markdown to HTML.
        """
        logging.info("Running Pandoc to convert markdown to HTML.")
        # Absolute path to the stylesheet
        style_css_path = os.path.abspath(os.path.join(self.styles_path, self.STYLE_CSS_FILENAME))
        logging.debug(f"Style CSS path: {style_css_path}")

        if not os.path.exists(style_css_path):
            logging.error(f"Style CSS file not found at {style_css_path}")
            raise FileNotFoundError(f"Style CSS file not found at {style_css_path}")

        # Absolute path to the temporary output HTML file
        temp_output_path = os.path.join(os.path.dirname(self.output_file), 'temp_output.html')

        command = [
            'pandoc', self.md_file,
            '-f', 'markdown+autolink_bare_uris+hard_line_breaks',
            '-c', style_css_path,  # Apply the custom style CSS
            '-s', '-o', temp_output_path,
            '--metadata', f'title={self.html_title}'
        ]
        logging.debug(f"Pandoc command: {' '.join(command)}")
        try:
            subprocess.run(command, check=True)
            logging.info("Pandoc conversion executed successfully.")
        except subprocess.CalledProcessError as e:
            logging.error(f"Pandoc conversion failed: {e}")
            raise

    def convert_urls_to_hyperlinks(self, html_content):
        """
        Converts plain URLs in HTML content to clickable hyperlinks.

        Args:
            html_content (str): The HTML content.

        Returns:
            str: Modified HTML content with hyperlinks.
        """
        logging.debug("Converting plain URLs to HTML hyperlinks.")
        soup = BeautifulSoup(html_content, 'html.parser')

        # Regex to find URLs
        url_regex = re.compile(r'(https?://\S+)')

        # Iterate over all text nodes in the document
        for text_node in soup.find_all(string=url_regex):
            new_content = []
            last_index = 0
            for match in url_regex.finditer(text_node):
                start, end = match.span()
                url = match.group(1)

                # Append text before the URL
                new_content.append(text_node[last_index:start])

                # Create a new <a> tag for the URL
                a_tag = soup.new_tag('a', href=url)
                a_tag.string = url
                new_content.append(a_tag)

                last_index = end

            # Append the remaining text after the last URL
            new_content.append(text_node[last_index:])

            # Replace the original text node with new content
            parent = text_node.parent
            for elem in new_content:
                if isinstance(elem, str):
                    parent.insert_before(elem)
                else:
                    parent.insert_before(elem)
            text_node.extract()

        logging.debug("Converted plain URLs to hyperlinks.")
        return str(soup)

    def post_process_html(self, html_content):
        """
        Performs post-processing on the HTML content to refine its structure and resources.

        Args:
            html_content (str): The initial HTML content.

        Returns:
            str: The final processed HTML content.
        """
        logging.info("Starting post-processing of HTML content.")
        soup = BeautifulSoup(html_content, 'html.parser')

        # Add a meta description tag for SEO and metadata purposes
        if self.meta_description and self.meta_description != "-":
            meta_tag = soup.new_tag('meta', attrs={'name': 'description', 'content': self.meta_description})
            soup.head.insert(0, meta_tag)
            logging.debug("Added meta description tag.")

        # Convert plain URLs within the content to clickable hyperlinks
        html_content_with_links = self.convert_urls_to_hyperlinks(str(soup))
        soup = BeautifulSoup(html_content_with_links, 'html.parser')

        # Handle image sources
        img_tags = soup.find_all('img')
        for img in img_tags:
            src = img.get('src', '')
            parsed_src = urlparse(src)

            # Check if this is the OASIS logo image
            if src == "https://docs.oasis-open.org/templates/OASISLogo-v3.0.png":
                logging.info("OASIS logo detected. It will be inserted at the specified location.")
                img.decompose()  # Remove existing OASIS logo images to avoid duplicates
                continue  # Will insert the desired OASIS logo later

            # Handle absolute URLs: Download the image and save it locally
            if parsed_src.scheme in ['http', 'https']:
                image_filename = os.path.basename(parsed_src.path)
                local_image_path = os.path.join(self.images_dir, image_filename)
                relative_image_path = os.path.join(self.IMAGES_SUBDIR, image_filename)

                if not os.path.exists(local_image_path):
                    try:
                        logging.info(f"Downloading image from {src} to {local_image_path}")
                        response = requests.get(src, timeout=10)
                        response.raise_for_status()
                        with open(local_image_path, 'wb') as f:
                            f.write(response.content)
                        logging.info(f"Successfully downloaded {src}")
                    except RequestException as e:
                        logging.error(f"Failed to download image {src}: {e}")
                        img.decompose()  # Remove the image if download fails
                        continue  # Skip updating the src if download fails

                # Update the src attribute to the relative path of the downloaded image
                img['src'] = relative_image_path
                logging.debug(f"Updated image src to relative path: {img['src']}")

            else:
                # Handle relative image paths (assuming they are already correct)
                logging.debug(f"Found relative image src: {src}. No action taken.")

        # Insert the OASIS logo <img> tag immediately after the <body> tag
        if not soup.body.find('img', src="https://docs.oasis-open.org/templates/OASISLogo-v3.0.png"):
            logging.info("Inserting OASIS logo at the specified location.")
            oasis_logo_tag = BeautifulSoup(self.LOGO_IMG_TAG, 'html.parser')
            if soup.body:
                # Insert as the first child of <body>
                soup.body.insert(0, oasis_logo_tag)
                logging.debug("OASIS logo inserted successfully.")
            else:
                logging.warning("<body> tag not found. OASIS logo not inserted.")

        # Ensure all <hr> tags follow the stylesheet's behavior by removing inline styles
        hr_tags = soup.find_all('hr')
        for hr in hr_tags:
            if hr.has_attr('style'):
                del hr['style']
                logging.debug("Removed inline style from <hr> tag to adhere to stylesheet.")

        # Remove any existing <style> tags to prevent duplication
        existing_style_tags = soup.find_all('style')
        for style in existing_style_tags:
            style.decompose()
            logging.debug("Removed existing <style> tag to prevent duplication.")

        # Inject the custom CSS by linking to the stylesheet
        # Calculate the relative path from the HTML file to the stylesheet
        style_css_relative_path = os.path.relpath(
            os.path.join(self.styles_path, self.STYLE_CSS_FILENAME),
            os.path.dirname(self.output_file)
        )
        link_tag = soup.new_tag('link', rel='stylesheet', href=style_css_relative_path)
        soup.head.append(link_tag)
        logging.debug(f"Injected custom CSS via <link> tag with href='{style_css_relative_path}'.")

        # Optionally, add a <base> tag if needed (as per sample HTML)
        # Uncomment the following lines if a <base> tag is required
        # if not soup.head.find('base'):
        #     base_tag = soup.new_tag('base', href="https://docs.oasis-open.org/ap-pf/v1.0/ap-pf/v1.0/csd02/ap-pf-v1.0-csd02.html")
        #     soup.head.insert(0, base_tag)
        #     logging.debug("Added <base> tag to <head>.")

        # Finalize the HTML content
        final_html = str(soup)
        logging.info("Completed post-processing of HTML content.")
        return final_html

    def ensure_toc_title(self):
        """
        Ensures that the Table of Contents (TOC) in the Markdown file has a title.
        """
        logging.info("Ensuring TOC title is present.")
        try:
            with open(self.md_file, 'r', encoding='utf-8') as file:
                lines = file.readlines()

            toc_present = any(re.match(r'^- \[.*\]\(.*\)', line) for line in lines)
            toc_title_present = any(re.match(r'^\s*#+\s*Table of Contents\s*$', line, re.IGNORECASE) for line in lines)

            if toc_present and not toc_title_present:
                # Find the first TOC entry
                for i, line in enumerate(lines):
                    if re.match(r'^- \[.*\]\(.*\)', line):
                        toc_index = i
                        break
                else:
                    toc_index = None

                if toc_index is not None:
                    # Determine the appropriate heading level for TOC
                    first_heading = re.search(r'^(#+)\s+.*', lines[0])
                    if first_heading:
                        heading_level = len(first_heading.group(1)) + 1
                        toc_heading = '#' * heading_level + ' Table of Contents\n'
                    else:
                        toc_heading = '# Table of Contents\n'

                    lines.insert(toc_index, toc_heading)
                    logging.info("Table of Contents title added.")

                    # Write the updated content back to the Markdown file
                    with open(self.md_file, 'w', encoding='utf-8') as file:
                        file.writelines(lines)
                    logging.debug(f"Inserted TOC title at line {toc_index + 1}.")
            else:
                logging.info("No changes needed for TOC title.")
        except Exception as e:
            logging.error(f"Error ensuring TOC title: {e}")

    def run_prettier(self):
        """
        Runs Prettier to format the Markdown file for consistent styling.
        """
        logging.info("Running Prettier to format Markdown file.")
        sanitized_md_file = self.md_file.strip()  # Ensure file path is sanitized
        command = ['prettier', '--write', sanitized_md_file]
        logging.debug(f"Prettier command: {' '.join(command)}")
        try:
            subprocess.run(command, check=True)
            logging.info("Prettier formatting completed successfully.")
        except subprocess.CalledProcessError as e:
            logging.error(f"Prettier formatting failed: {e}")
            raise

    def convert(self):
        """
        Converts the Markdown file to HTML with post-processing.
        """
        temp_output = os.path.join(os.path.dirname(self.output_file), 'temp_output.html')
        try:
            logging.info("Starting Markdown to HTML conversion process.")

            # Step 1: Ensure the TOC title is added (if necessary)
            self.ensure_toc_title()

            # Step 2: Run Prettier to format the Markdown file (if required)
            # This can be controlled externally via arguments; already handled in main

            # Step 3: Run Pandoc to convert Markdown to HTML
            self.run_pandoc()

            # Step 4: Read the generated HTML content from the temporary file
            html_content = self.read_file(temp_output)

            # Step 5: Post-process the HTML content (embedding CSS, handling images, etc.)
            final_html = self.post_process_html(html_content)

            # Step 6: Write the final processed HTML to the output file
            self.write_file(self.output_file, final_html)
            logging.info(f"HTML conversion and post-processing completed successfully. Output file: {self.output_file}")

        except Exception as e:
            logging.error(f"An error occurred during conversion: {e}")
            raise
        finally:
            # Ensure the temporary file is deleted to clean up
            if os.path.exists(temp_output):
                os.remove(temp_output)
                logging.debug(f"Temporary file {temp_output} deleted.")

def main():
    """
    The main entry point of the script.
    """
    # Set up argument parsing
    parser = argparse.ArgumentParser(description='Markdown to HTML Converter with Custom Styling')
    parser.add_argument('md_file', type=str, help='Path to the Markdown file')
    parser.add_argument('git_repo_basedir', type=str, help='Base directory of git repository')
    parser.add_argument('md_dir', type=str, help='Directory containing the Markdown file')
    parser.add_argument('--test', action='store_true', help='Run in test mode')
    parser.add_argument('--md-format', action='store_true', help='Run Prettier to format the Markdown file')
    parser.add_argument('--md-to-html', action='store_true', help='Convert Markdown file to HTML')

    args = parser.parse_args()

    if args.test:
        # **Test Mode: Align with GitHub Workflow**
        # Assuming the Markdown file is named 'example.md' in the main directory
        git_repo_basedir = '/github/workspace'
        md_dir = git_repo_basedir  # Main directory
        md_file = os.path.join(md_dir, 'example.md')
        output_file = os.path.join(md_dir, 'example.html')
        logging.info("Running in test mode with paths aligned to GitHub workflow.")
        logging.info(f"Markdown File: {md_file}")
        logging.info(f"Output File: {output_file}")
    else:
        # Use paths from arguments
        git_repo_basedir = sanitize_file_path(args.git_repo_basedir)
        md_dir = sanitize_file_path(args.md_dir)
        md_file = sanitize_file_path(args.md_file)
        output_file = os.path.join(md_dir, os.path.basename(md_file).replace('.md', '.html'))
        logging.info("Running in normal mode with provided arguments.")
        logging.info(f"Markdown File: {md_file}")
        logging.info(f"Output File: {output_file}")

    # Initialize the converter with the sanitized paths
    converter = MarkdownToHtmlConverter(md_file, output_file, git_repo_basedir, md_dir)

    if args.md_format:
        # Run Prettier to format the Markdown file
        converter.run_prettier()
        logging.info('Markdown formatting completed.')

    if args.md_to_html:
        # Convert Markdown to HTML
        converter.convert()
        logging.info('Markdown to HTML conversion completed.')

if __name__ == '__main__':
    main()
