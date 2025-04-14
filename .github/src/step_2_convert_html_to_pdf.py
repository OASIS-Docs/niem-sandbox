#!/usr/bin/env python3

import sys
import os
import subprocess
import logging
from datetime import datetime

# Initialize logging to print to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class PDFGenerator:
    def __init__(self, html_file, pdf_file, date_str):
        self.html_file = html_file
        self.pdf_file = pdf_file
        self.date_str = date_str

    def generate_pdf(self):
        try:
            # Parse the date string
            date_obj = datetime.strptime(self.date_str, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%d %B %Y')
            year = date_obj.strftime('%Y')

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
                self.html_file,
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
    parser = argparse.ArgumentParser(description='Convert HTML to PDF')
    parser.add_argument('html_file', type=str, help='The HTML file to convert')
    parser.add_argument('date_str', type=str, help='The date string in yyyy-mm-dd format')
    args = parser.parse_args()

    main(args.html_file, args.date_str)
