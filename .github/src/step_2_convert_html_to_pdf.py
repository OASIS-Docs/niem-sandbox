#!/usr/bin/env python3

import sys
import os
import subprocess
import logging
from datetime import datetime
from pathlib import Path

# Initialize logging to print to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

OASIS_CSS_URL = 'https://docs.oasis-open.org/templates/css/markdown-styles-v1.7.3a.css'

class PDFGenerator:
    def __init__(self, html_file, pdf_file, date_str):
        self.html_file = html_file
        self.pdf_file = pdf_file
        self.date_str = date_str

    def inject_css_inline(self, html_path):
        import requests

        logging.info("Injecting remote stylesheet into HTML as inline <style> block")
        css_resp = requests.get(OASIS_CSS_URL)
        css_resp.raise_for_status()
        css_content = css_resp.text

        with open(html_path, 'r', encoding='utf-8') as f:
            html = f.read()

        # Replace <link href=OASIS> with <style>...</style>
        html = html.replace(
            f'<link rel="stylesheet" href="{OASIS_CSS_URL}" />',
            f'<style>\n{css_content}\n</style>'
        )

        temp_path = Path(html_path).with_name(f"{Path(html_path).stem}-inline.html")
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(html)

        return str(temp_path)

    def generate_pdf(self):
        try:
            # Parse the date string
            date_obj = datetime.strptime(self.date_str, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%d %B %Y')
            year = date_obj.strftime('%Y')

            # Inline CSS
            processed_html = self.inject_css_inline(self.html_file)

            cli_command = [
                'wkhtmltopdf',
                '--enable-local-file-access',
                '--page-size', 'Letter',
                '-T', '25', '-B', '20',
                '--header-spacing', '6',
                '--header-font-size', '10',
                '--header-center', 'Non-Standards Track Work Product',
                '--footer-line',
                '--footer-spacing', '4',
                '--footer-left', '',
                '--footer-center', f'Copyright © OASIS Open {year}. All Rights Reserved.',
                '--footer-right', f'{formatted_date}  - Page [page] of [topage]',
                '--footer-font-size', '8',
                '--footer-font-name', 'LiberationSans',
                '--no-outline',
                processed_html,
                self.pdf_file
            ]
            logging.info('Generating PDF with command: %s', ' '.join(cli_command))
            subprocess.run(cli_command, check=True)
            logging.info('PDF generated successfully: %s', self.pdf_file)
        except subprocess.CalledProcessError as e:
            logging.exception('Error in generating PDF: %s', str(e))
            raise
        except Exception as e:
            logging.exception('Unexpected error during PDF generation: %s', str(e))
            raise

def main(html_file, date_str):
    logging.info('Starting PDF generation process for HTML file: %s', html_file)
    pdf_file = html_file.replace('.html', '.pdf')

    try:
        pdf_generator = PDFGenerator(html_file, pdf_file, date_str)
        pdf_generator.generate_pdf()
        logging.info('PDF generation completed. Output file: %s', pdf_file)
    except Exception as e:
        logging.exception('Unexpected error: %s', str(e))
        sys.exit(1)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Convert HTML to PDF with inlined CSS')
    parser.add_argument('html_file', type=str, help='The HTML file to convert')
    parser.add_argument('date_str', type=str, help='The date string in yyyy-mm-dd format')
    args = parser.parse_args()

    main(args.html_file, args.date_str)
