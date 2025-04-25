#!/usr/bin/env python3

import sys
import os
import re
import subprocess
import logging
from datetime import datetime
from pathlib import Path

# Initialize logging to print to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Hardcoded stylesheet (upgraded for Mikey, 2025-04-14) with narrow fonts and minimal styling for code blocks.
RAW_INLINE_CSS = """
<style>
/* OASIS specification styles for HTML generated from Markdown or similar sources */

body {
    margin-left: 0.5cm;
    margin-right: 0.5cm;
    font-family: LiberationSans, Arial, Helvetica, sans-serif;
    font-size: 12pt;
    line-height: 1.2;
}

html {
    overflow-x: auto;
}

h1 { font-size: 18pt; }
h2 { font-size: 14pt; }
h3 { font-size: 13pt; }
h4 { font-size: 12pt; }
h5 { font-size: 11pt; }
h1big { font-size: 24pt; }
h1, h2, h3, h4, h5, h1big {
    font-family: LiberationSans, Arial, Helvetica, sans-serif;
    font-weight: bold;
    margin: 8pt 0;
    color: #446CAA;
}

/* style for gray "OASIS Committee Note" text */
h1gray {
    font-size: 18pt;
    font-family: LiberationSans, Arial, Helvetica, sans-serif;
    font-weight: bold;
    color: #717171;
}

/* style for h6, for use as Reference tag */
h6 {
    font-size: 12pt;
    line-height: 1.0;
    font-family: LiberationSans, Arial, Helvetica, sans-serif;
    font-weight: bold;
    margin: 0pt;
}

/* Fix applied: Avoid page break before <hr> */
hr {
    page-break-before: avoid;
}

/* Table styles - bordered with option for striped */
table {
    border-collapse: collapse;
    width: 100%;
    display: table;
    font-size: 12pt;
    margin-top: 6pt;
}

table, th, td {
    border: 1pt solid black;
    padding: 6pt 6pt;
    text-align: left;
    vertical-align: top;
}

th {
    color: #ffffff;
    background-color: #1a8cff;
}

/* Inline Code */
code {
  font-family: "Source Code Pro", "Liberation Mono", monospace;
  font-size: 9pt;
  background-color: #eeeeee;
  color: #111;
  border: 1px solid #ccc;
  border-radius: 3px;
  padding: 2px 5px;
  white-space: nowrap;
}

/* Block code */
pre {
  font-family: "Source Code Pro", "Liberation Mono", monospace;
  font-size: 9pt;
  line-height: 1.4;
  background-color: #eeeeee;
  color: #111;
  white-space: pre;
  overflow-x: auto;
  box-sizing: border-box;
  padding: 10px;
  margin: 10px 0;
  border: 1px solid #ccc;
  border-radius: 6px;
  width: 100%;
  max-width: 100vw;
}

/* remove ALL layout from nested code */
pre code {
  font-family: inherit;
  font-size: 8pt;
  line-height: inherit;
  background: inherit;
  overflow-x: auto;
  color: inherit;
  white-space: inherit;
  padding: 0;
  margin: 0;
  border: none;
  width: 100%;
  max-width: 100vw;
  display: block;
}

/* Offset block quote */
blockquote {
    border-left: 5px solid #ccc;
    padding-left: 10px;
}
</style>
"""

# Define markers for our injected CSS block.
INLINE_CSS_MARKER_BEGIN = "<!-- BEGIN INLINE CSS -->"
INLINE_CSS_MARKER_END = "<!-- END INLINE CSS -->"
# Build the full block to inject.
INLINE_CSS_BLOCK = INLINE_CSS_MARKER_BEGIN + "\n" + RAW_INLINE_CSS + "\n" + INLINE_CSS_MARKER_END

class PDFGenerator:
    def __init__(self, html_file, pdf_file, date_str):
        self.html_file = html_file
        self.pdf_file = pdf_file
        self.date_str = date_str

    def inject_css_inline(self, html_path):
        logging.info("Injecting hardcoded CSS into HTML as an inline <style> block")
        with open(html_path, 'r', encoding='utf-8') as f:
            html = f.read()

        # Remove any previously injected CSS marked with our unique markers.
        html = re.sub(r'<!-- BEGIN INLINE CSS -->.*?<!-- END INLINE CSS -->', '', html, flags=re.DOTALL)

        # Insert the new INLINE_CSS_BLOCK. Preferably before the closing </head> tag.
        if '</head>' in html:
            html = html.replace('</head>', INLINE_CSS_BLOCK + "\n</head>")
        elif '<head>' in html:
            html = html.replace('<head>', '<head>\n' + INLINE_CSS_BLOCK)
        else:
            # If no <head> tag exists, prepend it.
            html = INLINE_CSS_BLOCK + html

        # Determine the output path.
        # If the current file name already contains '-inline', overwrite in place.
        input_path = Path(html_path)
        if "-inline" in input_path.stem:
            out_path = input_path
        else:
            out_path = input_path.with_name(f"{input_path.stem}-inline{input_path.suffix}")

        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(html)

        logging.info("Injected CSS saved to: %s", str(out_path))
        return str(out_path)

    def generate_pdf(self):
        try:
            # Parse the date string.
            date_obj = datetime.strptime(self.date_str, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%d %B %Y')
            year = date_obj.strftime('%Y')

            # Process HTML to inject inline CSS.
            processed_html = self.inject_css_inline(self.html_file)

            cli_command = [
                'wkhtmltopdf',
                '--debug-javascript',
                '--enable-local-file-access',
                '--page-size', 'Letter',
                '-T', '25', '-B', '20',
                '--header-spacing', '6',
                '--header-font-size', '10',
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
    parser = argparse.ArgumentParser(description='Convert HTML to PDF with inlined CSS, ensuring no duplicate inline blocks')
    parser.add_argument('html_file', type=str, help='The HTML file to convert')
    parser.add_argument('date_str', type=str, help='The date string in yyyy-mm-dd format')
    args = parser.parse_args()
    main(args.html_file, args.date_str)
