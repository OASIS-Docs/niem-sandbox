#!/usr/bin/env python3
"""
Enterprise-grade Markdown to HTML Converter
Modular, extensible, and performance-optimized conversion pipeline
"""

import os
import sys
import subprocess
import argparse
import logging
import asyncio
import aiohttp
import aiofiles
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Union
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
import json
import hashlib
import time
from urllib.parse import urlparse, urljoin
import re
from abc import ABC, abstractmethod

# Third-party imports
from bs4 import BeautifulSoup, Tag
import requests
from requests.exceptions import RequestException
import shutil


@dataclass
class ConversionConfig:
    """Configuration for the conversion process"""
    style_css_filename: str = 'markdown-styles-v1.8.1-cn_final.css'
    style_css_url: str = 'https://docs.oasis-open.org/templates/css/markdown-styles-v1.8.1-cn_final.css'
    logo_img_tag: str = '<img alt="OASIS Logo" src="https://docs.oasis-open.org/templates/OASISLogo-v3.0.png"/>'
    images_subdir: str = 'images'
    styles_subdir: str = 'styles'
    download_timeout: int = 30
    max_concurrent_downloads: int = 5
    cache_images: bool = True
    validate_links: bool = True
    enable_async: bool = True


@dataclass
class ConversionContext:
    """Context object containing all conversion state"""
    md_file: Path
    output_file: Path
    git_repo_basedir: Optional[Path] = None
    md_dir: Optional[Path] = None
    config: ConversionConfig = field(default_factory=ConversionConfig)
    
    # Derived paths
    images_dir: Optional[Path] = field(init=False)
    styles_dir: Optional[Path] = field(init=False)
    
    # Metadata
    meta_description: str = field(init=False, default="-")
    html_title: str = field(init=False, default="-")
    
    def __post_init__(self):
        """Initialize derived paths and ensure directories exist"""
        self.images_dir = self.output_file.parent / self.config.images_subdir
        self.styles_dir = self.output_file.parent / self.config.styles_subdir
        
        # Ensure directories exist
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.styles_dir.mkdir(parents=True, exist_ok=True)


class Logger:
    """Enhanced logging with structured output and performance metrics"""
    
    def __init__(self, name: str = __name__, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        # Remove existing handlers to avoid duplication
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # Create formatters
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        console_formatter = logging.Formatter(
            '%(levelname)s - %(funcName)s - %(message)s'
        )
        
        # File handler
        file_handler = logging.FileHandler("markdown_conversion.log")
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
    
    def performance_log(self, operation: str, duration: float, **kwargs):
        """Log performance metrics"""
        self.logger.info(f"PERF: {operation} completed in {duration:.3f}s", extra=kwargs)


class ConversionError(Exception):
    """Custom exception for conversion errors"""
    pass


class ProcessorBase(ABC):
    """Base class for all processors in the conversion pipeline"""
    
    def __init__(self, logger: Logger):
        self.logger = logger
    
    @abstractmethod
    async def process(self, context: ConversionContext) -> ConversionContext:
        """Process the conversion context"""
        pass


class MetadataExtractor(ProcessorBase):
    """Extracts metadata from markdown files with caching"""
    
    def __init__(self, logger: Logger):
        super().__init__(logger)
        self._cache: Dict[str, Dict[str, str]] = {}
    
    async def process(self, context: ConversionContext) -> ConversionContext:
        """Extract metadata from markdown file"""
        start_time = time.time()
        
        # Check cache first
        file_hash = self._get_file_hash(context.md_file)
        if file_hash in self._cache:
            cached_data = self._cache[file_hash]
            context.meta_description = cached_data.get('description', '-')
            context.html_title = cached_data.get('title', '-')
            self.logger.logger.debug("Used cached metadata")
            return context
        
        try:
            async with aiofiles.open(context.md_file, 'r', encoding='utf-8') as file:
                content = await file.read()
            
            # Extract metadata concurrently
            description_task = asyncio.create_task(self._extract_description(content))
            title_task = asyncio.create_task(self._extract_title(content))
            
            context.meta_description, context.html_title = await asyncio.gather(
                description_task, title_task
            )
            
            # Cache the results
            self._cache[file_hash] = {
                'description': context.meta_description,
                'title': context.html_title
            }
            
            self.logger.performance_log(
                "metadata_extraction", 
                time.time() - start_time,
                file=str(context.md_file)
            )
            
        except Exception as e:
            self.logger.logger.error(f"Error extracting metadata: {e}")
            raise ConversionError(f"Metadata extraction failed: {e}")
        
        return context
    
    def _get_file_hash(self, file_path: Path) -> str:
        """Generate hash for file caching"""
        stat = file_path.stat()
        return hashlib.md5(f"{file_path}:{stat.st_mtime}:{stat.st_size}".encode()).hexdigest()
    
    async def _extract_description(self, content: str) -> str:
        """Extract meta description from content"""
        description_pattern = r'<!--.*?description:\s*(.*?)\s*-->'
        match = re.search(description_pattern, content, re.DOTALL)
        if match:
            description = match.group(1).strip()
            self.logger.logger.info(f"Meta description extracted: {description}")
            return description
        return "-"
    
    async def _extract_title(self, content: str) -> str:
        """Extract HTML title from content"""
        title_pattern = r'^#\s+(.+)$'
        match = re.search(title_pattern, content, re.MULTILINE)
        if match:
            title = match.group(1).strip()
            self.logger.logger.info(f"HTML title extracted: {title}")
            return title
        return "-"


class StylesheetManager(ProcessorBase):
    """Manages CSS stylesheets with async downloads and validation"""
    
    async def process(self, context: ConversionContext) -> ConversionContext:
        """Ensure stylesheet is available"""
        start_time = time.time()
        
        stylesheet_path = context.styles_dir / context.config.style_css_filename
        
        if not stylesheet_path.exists():
            self.logger.logger.warning(f"Stylesheet not found at {stylesheet_path}, downloading...")
            await self._download_stylesheet(context.config.style_css_url, stylesheet_path)
            await self._commit_stylesheet(context, stylesheet_path)
        else:
            self.logger.logger.info(f"Stylesheet exists at {stylesheet_path}")
        
        self.logger.performance_log("stylesheet_management", time.time() - start_time)
        return context
    
    async def _download_stylesheet(self, url: str, destination: Path):
        """Download stylesheet asynchronously"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    content = await response.read()
                    
                    async with aiofiles.open(destination, 'wb') as f:
                        await f.write(content)
                    
                    self.logger.logger.info(f"Downloaded stylesheet: {url} -> {destination}")
        except Exception as e:
            self.logger.logger.error(f"Failed to download stylesheet: {e}")
            raise ConversionError(f"Stylesheet download failed: {e}")
    
    async def _commit_stylesheet(self, context: ConversionContext, stylesheet_path: Path):
        """Commit stylesheet to git repository"""
        if not context.git_repo_basedir:
            return
        
        try:
            # Configure git
            await self._run_git_command(['git', 'config', '--global', 'user.name', 'Markdown Converter Bot'], context.git_repo_basedir)
            await self._run_git_command(['git', 'config', '--global', 'user.email', 'converter-bot@example.com'], context.git_repo_basedir)
            
            # Add and commit
            relative_path = stylesheet_path.relative_to(context.git_repo_basedir)
            await self._run_git_command(['git', 'add', str(relative_path)], context.git_repo_basedir)
            await self._run_git_command(['git', 'commit', '-m', f'Add stylesheet: {context.config.style_css_filename}'], context.git_repo_basedir)
            await self._run_git_command(['git', 'push'], context.git_repo_basedir)
            
            self.logger.logger.info("Stylesheet committed and pushed successfully")
        except Exception as e:
            self.logger.logger.error(f"Git operations failed: {e}")
            # Don't raise here - stylesheet download succeeded
    
    async def _run_git_command(self, cmd: List[str], cwd: Path):
        """Run git command asynchronously"""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, cmd, stdout, stderr)


class PandocConverter(ProcessorBase):
    """Handles Pandoc conversion with advanced configuration"""
    
    async def process(self, context: ConversionContext) -> ConversionContext:
        """Convert markdown to HTML using Pandoc"""
        start_time = time.time()
        
        temp_output = context.output_file.parent / 'temp_output.html'
        stylesheet_path = context.styles_dir / context.config.style_css_filename
        
        if not stylesheet_path.exists():
            raise ConversionError(f"Stylesheet not found: {stylesheet_path}")
        
        cmd = [
            'pandoc', str(context.md_file),
            '-f', 'markdown+autolink_bare_uris+hard_line_breaks+smart+pipe_tables+yaml_metadata_block',
            '-t', 'html5',
            '-c', str(stylesheet_path.resolve()),
            '-s', '-o', str(temp_output),
            '--metadata', f'title={context.html_title}',
            '--toc', '--toc-depth=3',
            '--highlight-style=tango',
            '--mathjax'
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, cmd, stdout, stderr)
            
            # Store temp output path for post-processing
            context.temp_output = temp_output
            
            self.logger.performance_log("pandoc_conversion", time.time() - start_time)
            self.logger.logger.info("Pandoc conversion completed successfully")
            
        except Exception as e:
            self.logger.logger.error(f"Pandoc conversion failed: {e}")
            raise ConversionError(f"Pandoc conversion failed: {e}")
        
        return context


class HtmlPostProcessor(ProcessorBase):
    """Advanced HTML post-processing with concurrent image handling"""
    
    def __init__(self, logger: Logger):
        super().__init__(logger)
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def process(self, context: ConversionContext) -> ConversionContext:
        """Post-process HTML with advanced features"""
        start_time = time.time()
        
        # Read HTML content
        async with aiofiles.open(context.temp_output, 'r', encoding='utf-8') as f:
            html_content = await f.read()
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Apply transformations
        await self._add_meta_tags(soup, context)
        await self._process_images(soup, context)
        await self._convert_urls_to_links(soup)
        await self._add_oasis_logo(soup, context)
        await self._inject_custom_styles(soup, context)
        await self._optimize_html_structure(soup)
        
        # Write final HTML
        final_html = str(soup)
        async with aiofiles.open(context.output_file, 'w', encoding='utf-8') as f:
            await f.write(final_html)
        
        # Cleanup temp file
        context.temp_output.unlink(missing_ok=True)
        
        self.logger.performance_log("html_post_processing", time.time() - start_time)
        return context
    
    async def _add_meta_tags(self, soup: BeautifulSoup, context: ConversionContext):
        """Add comprehensive meta tags"""
        if not soup.head:
            return
        
        # Meta description
        if context.meta_description != "-":
            meta_desc = soup.new_tag('meta', attrs={'name': 'description', 'content': context.meta_description})
            soup.head.insert(0, meta_desc)
        
        # Additional SEO meta tags
        meta_tags = [
            ('viewport', 'width=device-width, initial-scale=1.0'),
            ('charset', 'utf-8'),
            ('generator', 'Enterprise Markdown Converter'),
            ('author', 'OASIS Technical Committee')
        ]
        
        for name, content in meta_tags:
            if name == 'charset':
                tag = soup.new_tag('meta', charset=content)
            else:
                tag = soup.new_tag('meta', attrs={'name': name, 'content': content})
            soup.head.insert(0, tag)
    
    async def _process_images(self, soup: BeautifulSoup, context: ConversionContext):
        """Process images with concurrent downloads"""
        img_tags = soup.find_all('img')
        if not img_tags:
            return
        
        # Create session for image downloads
        connector = aiohttp.TCPConnector(limit=context.config.max_concurrent_downloads)
        timeout = aiohttp.ClientTimeout(total=context.config.download_timeout)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tasks = []
            for img in img_tags:
                src = img.get('src', '')
                if self._is_external_url(src) and not self._is_oasis_logo(src):
                    task = self._process_single_image(session, img, src, context)
                    tasks.append(task)
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _process_single_image(self, session: aiohttp.ClientSession, img_tag: Tag, src: str, context: ConversionContext):
        """Process a single image download"""
        try:
            parsed_url = urlparse(src)
            filename = Path(parsed_url.path).name or 'image.png'
            local_path = context.images_dir / filename
            relative_path = f"{context.config.images_subdir}/{filename}"
            
            if not local_path.exists() or not context.config.cache_images:
                async with session.get(src) as response:
                    response.raise_for_status()
                    content = await response.read()
                    
                    async with aiofiles.open(local_path, 'wb') as f:
                        await f.write(content)
                
                self.logger.logger.info(f"Downloaded image: {src} -> {local_path}")
            
            # Update img tag
            img_tag['src'] = relative_path
            
        except Exception as e:
            self.logger.logger.error(f"Failed to process image {src}: {e}")
            img_tag.decompose()  # Remove failed images
    
    def _is_external_url(self, url: str) -> bool:
        """Check if URL is external"""
        parsed = urlparse(url)
        return parsed.scheme in ('http', 'https')
    
    def _is_oasis_logo(self, url: str) -> bool:
        """Check if URL is the OASIS logo"""
        return "OASISLogo" in url
    
    async def _convert_urls_to_links(self, soup: BeautifulSoup):
        """Convert plain URLs to clickable links"""
        url_pattern = re.compile(r'(https?://\S+)')
        
        for text_node in soup.find_all(string=url_pattern):
            if text_node.parent.name in ['a', 'code', 'pre']:
                continue  # Skip if already in link or code
            
            new_content = []
            last_index = 0
            
            for match in url_pattern.finditer(text_node):
                start, end = match.span()
                url = match.group(1)
                
                # Add text before URL
                if start > last_index:
                    new_content.append(text_node[last_index:start])
                
                # Create link
                a_tag = soup.new_tag('a', href=url, target='_blank', rel='noopener noreferrer')
                a_tag.string = url
                new_content.append(a_tag)
                
                last_index = end
            
            # Add remaining text
            if last_index < len(text_node):
                new_content.append(text_node[last_index:])
            
            # Replace original text
            parent = text_node.parent
            for item in new_content:
                parent.insert_before(item, text_node)
            text_node.extract()
    
    async def _add_oasis_logo(self, soup: BeautifulSoup, context: ConversionContext):
        """Add OASIS logo to the document"""
        if soup.body and not soup.body.find('img', src=lambda x: x and 'OASISLogo' in x):
            logo_soup = BeautifulSoup(context.config.logo_img_tag, 'html.parser')
            soup.body.insert(0, logo_soup.img)
    
    async def _inject_custom_styles(self, soup: BeautifulSoup, context: ConversionContext):
        """Inject custom CSS with relative paths"""
        if not soup.head:
            return
        
        # Remove existing style tags to prevent conflicts
        for style_tag in soup.find_all('style'):
            style_tag.decompose()
        
        # Add stylesheet link
        stylesheet_relative = os.path.relpath(
            context.styles_dir / context.config.style_css_filename,
            context.output_file.parent
        )
        
        link_tag = soup.new_tag('link', rel='stylesheet', href=stylesheet_relative)
        soup.head.append(link_tag)
    
    async def _optimize_html_structure(self, soup: BeautifulSoup):
        """Optimize HTML structure for performance and accessibility"""
        # Remove inline styles from hr tags
        for hr_tag in soup.find_all('hr'):
            if hr_tag.has_attr('style'):
                del hr_tag['style']
        
        # Add lang attribute to html tag
        if soup.html and not soup.html.has_attr('lang'):
            soup.html['lang'] = 'en'
        
        # Ensure all images have alt text
        for img in soup.find_all('img'):
            if not img.get('alt'):
                img['alt'] = 'Image'


class TOCProcessor(ProcessorBase):
    """Handles Table of Contents processing"""
    
    async def process(self, context: ConversionContext) -> ConversionContext:
        """Ensure TOC has proper title"""
        start_time = time.time()
        
        async with aiofiles.open(context.md_file, 'r', encoding='utf-8') as f:
            content = await f.read()
        
        lines = content.splitlines()
        
        # Check if TOC exists without title
        toc_entries = [i for i, line in enumerate(lines) if re.match(r'^- \[.*\]\(.*\)', line)]
        toc_titles = [i for i, line in enumerate(lines) if re.match(r'^\s*#+\s*Table of Contents\s*$', line, re.IGNORECASE)]
        
        if toc_entries and not toc_titles:
            first_toc_index = toc_entries[0]
            
            # Determine heading level
            first_heading_match = re.search(r'^(#+)\s+.*', lines[0]) if lines else None
            heading_level = len(first_heading_match.group(1)) + 1 if first_heading_match else 2
            
            toc_title = '#' * heading_level + ' Table of Contents'
            lines.insert(first_toc_index, toc_title)
            
            # Write back to file
            async with aiofiles.open(context.md_file, 'w', encoding='utf-8') as f:
                await f.write('\n'.join(lines))
            
            self.logger.logger.info("Added Table of Contents title")
        
        self.logger.performance_log("toc_processing", time.time() - start_time)
        return context


class MarkdownFormatter(ProcessorBase):
    """Handles Prettier formatting"""
    
    async def process(self, context: ConversionContext) -> ConversionContext:
        """Format markdown file using Prettier"""
        start_time = time.time()
        
        cmd = ['prettier', '--write', str(context.md_file)]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, cmd, stdout, stderr)
            
            self.logger.performance_log("markdown_formatting", time.time() - start_time)
            self.logger.logger.info("Prettier formatting completed")
            
        except Exception as e:
            self.logger.logger.error(f"Prettier formatting failed: {e}")
            raise ConversionError(f"Markdown formatting failed: {e}")
        
        return context


class EnterpriseMarkdownConverter:
    """Main converter orchestrating the entire pipeline"""
    
    def __init__(self, config: Optional[ConversionConfig] = None):
        self.config = config or ConversionConfig()
        self.logger = Logger()
        
        # Initialize processors
        self.processors = {
            'metadata': MetadataExtractor(self.logger),
            'stylesheet': StylesheetManager(self.logger),  
            'toc': TOCProcessor(self.logger),
            'formatter': MarkdownFormatter(self.logger),
            'pandoc': PandocConverter(self.logger),
            'postprocess': HtmlPostProcessor(self.logger)
        }
    
    async def convert(self, 
                     md_file: Union[str, Path],
                     output_file: Union[str, Path],
                     git_repo_basedir: Optional[Union[str, Path]] = None,
                     md_dir: Optional[Union[str, Path]] = None,
                     format_markdown: bool = False,
                     convert_to_html: bool = True) -> ConversionContext:
        """Main conversion pipeline"""
        
        start_time = time.time()
        
        # Create context
        context = ConversionContext(
            md_file=Path(md_file),
            output_file=Path(output_file),
            git_repo_basedir=Path(git_repo_basedir) if git_repo_basedir else None,
            md_dir=Path(md_dir) if md_dir else None,
            config=self.config
        )
        
        try:
            # Execute pipeline stages
            context = await self.processors['metadata'].process(context)
            context = await self.processors['stylesheet'].process(context)
            context = await self.processors['toc'].process(context)
            
            if format_markdown:
                context = await self.processors['formatter'].process(context)
            
            if convert_to_html:
                context = await self.processors['pandoc'].process(context)
                context = await self.processors['postprocess'].process(context)
            
            total_time = time.time() - start_time
            self.logger.performance_log("total_conversion", total_time, 
                                      input_file=str(context.md_file),
                                      output_file=str(context.output_file))
            
            self.logger.logger.info(f"Conversion completed successfully: {context.output_file}")
            
        except Exception as e:
            self.logger.logger.error(f"Conversion failed: {e}")
            raise
        
        return context


async def main():
    """Async main entry point"""
    parser = argparse.ArgumentParser(description='Enterprise-grade Markdown to HTML Converter')
    parser.add_argument('md_file', type=str, help='Path to the Markdown file')
    parser.add_argument('git_repo_basedir', type=str, help='Base directory of git repository')
    parser.add_argument('md_dir', type=str, help='Directory containing the Markdown file')
    parser.add_argument('--test', action='store_true', help='Run in test mode')
    parser.add_argument('--md-format', action='store_true', help='Format Markdown file')
    parser.add_argument('--md-to-html', action='store_true', help='Convert to HTML')
    parser.add_argument('--config', type=str, help='Path to JSON config file')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], 
                       default='INFO', help='Logging level')
    
    args = parser.parse_args()
    
    # Load configuration
    config = ConversionConfig()
    if args.config and Path(args.config).exists():
        with open(args.config, 'r') as f:
            config_dict = json.load(f)
            config = ConversionConfig(**config_dict)
    
    # Configure logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # Determine paths
    if args.test:
        git_repo_basedir = Path('/github/workspace')
        md_dir = git_repo_basedir
        md_file = md_dir / 'example.md'
        output_file = md_dir / 'example.html'
    else:
        git_repo_basedir = Path(args.git_repo_basedir).resolve()
        md_dir = Path(args.md_dir).resolve()
        md_file = Path(args.md_file).resolve()
        output_file = md_dir / md_file.with_suffix('.html').name
    
    # Initialize converter and run
    converter = EnterpriseMarkdownConverter(config)
    
    try:
        await converter.convert(
            md_file=md_file,
            output_file=output_file,
            git_repo_basedir=git_repo_basedir,
            md_dir=md_dir,
            format_markdown=args.md_format,
            convert_to_html=args.md_to_html
        )
    except ConversionError as e:
        print(f"Conversion failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


def sync_main():
    """Synchronous wrapper for backwards compatibility"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Conversion interrupted by user", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    sync_main()
