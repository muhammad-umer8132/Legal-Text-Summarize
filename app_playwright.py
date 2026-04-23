#!/usr/bin/env python3
"""
Legal Text Summarizer using Gemini AI
Automates the analysis of legal documents using Google's Gemini AI through Playwright.
"""

import os
import re
import sys
import asyncio
import argparse
from pathlib import Path
from typing import Optional

import PyPDF2
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


def extract_text(file_path: str) -> Optional[str]:
    """
    Extract text from PDF or TXT files.
    
    Args:
        file_path: Path to the document file
        
    Returns:
        Extracted text or None if extraction fails
    """
    try:
        file_path = Path(file_path)
        
        if not file_path.exists():
            print(f"Error: File '{file_path}' does not exist.")
            return None
            
        if file_path.suffix.lower() == '.pdf':
            return extract_from_pdf(file_path)
        elif file_path.suffix.lower() == '.txt':
            return extract_from_txt(file_path)
        else:
            print(f"Error: Unsupported file type '{file_path.suffix}'. Supported types: PDF, TXT")
            return None
            
    except Exception as e:
        print(f"Error extracting text: {e}")
        return None


def extract_from_pdf(file_path: Path) -> str:
    """Extract text from PDF file using PyPDF2."""
    try:
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                text += page.extract_text() + "\n"
                
            return text
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""


def extract_from_txt(file_path: Path) -> str:
    """Extract text from TXT file."""
    try:
        # Try different encodings
        encodings = ['utf-8', 'utf-16', 'latin-1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as file:
                    return file.read()
            except UnicodeDecodeError:
                continue
                
        print(f"Error: Could not decode text file with any supported encoding.")
        return ""
        
    except Exception as e:
        print(f"Error reading text file: {e}")
        return ""


def clean_text(text: str) -> str:
    """
    Clean extracted text by removing page numbers and excessive whitespace.
    
    Args:
        text: Raw extracted text
        
    Returns:
        Cleaned text
    """
    if not text:
        return ""
    
    # Remove page numbers in various formats
    text = re.sub(r'Page\s+\d+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'-\s*\d+\s*-', '', text)
    text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)
    
    # Remove excessive blank lines (more than 2 consecutive)
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    
    # Strip extra whitespace from each line
    lines = [line.strip() for line in text.split('\n')]
    
    # Remove empty lines at start and end
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    
    return '\n'.join(lines)


def truncate_text(text: str, max_chars: int = 12000) -> str:
    """
    Truncate text to maximum character limit.
    
    Args:
        text: Text to truncate
        max_chars: Maximum number of characters
        
    Returns:
        Truncated text
    """
    if len(text) <= max_chars:
        return text
    
    # Truncate at word boundary if possible
    truncated = text[:max_chars]
    last_space = truncated.rfind(' ')
    
    if last_space > max_chars * 0.9:  # If we're close to the limit, use word boundary
        truncated = truncated[:last_space]
    
    return truncated + "\n\n[Note: Document was truncated to fit character limit]"


def build_prompt(case_text: str) -> str:
    """
    Build the combined prompt for Gemini AI.
    
    Args:
        case_text: Cleaned and truncated case text
        
    Returns:
        Complete prompt string
    """
    system_prompt = """[SYSTEM ROLE]: You are a highly experienced senior legal analyst, 
lawyer, and law professor with over 20 years of expertise in analyzing legal cases 
across multiple jurisdictions including common law, civil law, and constitutional law.

[YOUR TASK]: You will be given a legal case document. Your job is to read it carefully 
and produce a structured legal analysis using the IRAC method.

[STRICT OUTPUT FORMAT]: You must respond using EXACTLY these 6 sections in this exact order.
Each section must start on a new line with its label in capital letters followed by a colon.
Do not merge sections. Do not skip any section.

SHORT SUMMARY:
Write 4 to 6 clear sentences. Identify the parties involved, what happened, 
what legal action was taken, and what the final outcome was. 
Write as if explaining to a law student reading the case for the first time.

ISSUE:
State the central legal question or questions the court must decide. 
Be precise and specific. Frame it as a question. 
Example: "Does X owe a duty of care to Y in the absence of a direct contract?"

RULE:
List all applicable laws, statutes, legal principles, and precedents that 
govern this case. If specific case names or statute numbers are mentioned 
in the document, include them. Explain what each rule means in one sentence.

ANALYSIS:
This is the most important section. Apply the rules to the facts of this case.
Explain step by step how the law applies to what actually happened.
Present arguments from both sides where applicable.
Explain why the court decided the way it did.
Write at least 5 to 8 sentences with clear legal reasoning.

CONCLUSION:
State the final outcome of the case clearly and directly.
Mention which party won, what was decided, and what legal principle was confirmed.
If the case is ongoing or hypothetical, state the most likely outcome and why.
Write 3 to 4 sentences.

LEGAL ADVICE:
Write this section in plain simple English as if you are explaining to a 
person with no legal background whatsoever. No legal jargon allowed.
Tell them what this case means for people in similar situations.
Give practical actionable advice based on the outcome of this case.
Write 5 to 7 sentences.

[IMPORTANT RULES]:
- Never skip any of the 6 sections
- Always start each section with its label in capitals followed by a colon
- Never add extra sections or commentary outside the 6 sections
- Never write an introduction or conclusion outside the defined sections
- Base your analysis strictly on the facts provided in the case text
- If any information is missing from the case text, state that clearly within the section

[CASE TEXT]:"""

    return f"{system_prompt}\n\n{case_text}"


async def open_gemini_and_submit(prompt_text: str) -> Optional[str]:
    """
    Open browser, navigate to Gemini, and submit the prompt using Playwright.
    
    Args:
        prompt_text: Complete prompt to submit
        
    Returns:
        Response text or None if failed
    """
    playwright = await async_playwright().start()
    browser = None
    context = None
    
    try:
        # Launch browser
        print("Initializing browser...")
        browser = await playwright.chromium.launch(
            headless=False,  # Keep visible for user
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        
        # Create context with user agent
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1400, "height": 900},
            locale="en-US",
            timezone_id="America/New_York",
        )
        
        page = await context.new_page()
        
        # Navigate to Gemini
        print("Navigating to Gemini...")
        await page.goto("https://gemini.google.com/app", wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(5_000)
        
        # Wait for input field
        input_selectors = [
            "div[role='textbox'][contenteditable='true']",
            "div[contenteditable='true'][aria-label*='Ask']",
            "div[data-placeholder*='Ask Gemini']",
            "textarea[placeholder*='Ask Gemini']",
            "div[contenteditable='true']",
        ]
        
        input_element = None
        for selector in input_selectors:
            try:
                await page.wait_for_selector(selector, timeout=20_000, state="visible")
                input_element = page.locator(selector).first
                print("Found input field")
                break
            except PlaywrightTimeoutError:
                continue
        
        if not input_element:
            # Check if login is required
            body_text = (await page.locator("body").inner_text()).lower()
            if any(marker in body_text for marker in ["sign in", "log in", "to continue to gemini"]):
                print("Login required. Please complete sign-in in the browser window.")
                print("Waiting for login to complete...")
                
                # Wait for user to complete login
                for _ in range(90):  # Wait up to 3 minutes
                    await page.wait_for_timeout(2_000)
                    for selector in input_selectors:
                        try:
                            await page.wait_for_selector(selector, timeout=2_000, state="visible")
                            input_element = page.locator(selector).first
                            print("Login completed, found input field")
                            break
                        except PlaywrightTimeoutError:
                            continue
                    if input_element:
                        break
                else:
                    raise RuntimeError("Login timeout")
            else:
                raise RuntimeError("Could not find input field on Gemini page")
        
        # Input the prompt
        print("Submitting prompt to Gemini...")
        await input_element.click(force=True)
        
        try:
            await input_element.fill(prompt_text)
        except Exception:
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.keyboard.type(prompt_text, delay=15)
        
        await page.keyboard.press("Enter")
        
        # Wait for response
        print("Waiting for Gemini response...")
        response = await wait_for_stable_answer(page)
        
        return response
        
    except Exception as e:
        print(f"Error: {e}")
        return None
    finally:
        # Keep browser open for user reference
        print("\nBrowser will remain open for your reference. Close it manually when done.")
        # Don't close browser automatically - let user close it
        # The cleanup will happen when the script exits


async def wait_for_stable_answer(page, timeout_sec: int = 180, stable_checks: int = 3, interval_sec: int = 2) -> str:
    """
    Wait for Gemini to finish generating a stable response.
    
    Args:
        page: Playwright page object
        timeout_sec: Maximum time to wait
        stable_checks: Number of consistent checks needed
        interval_sec: Time between checks
        
    Returns:
        Stable response text
    """
    async def get_last_gemini_response():
        return await page.evaluate(
            """
            () => {
                const messages = document.querySelectorAll('message-content');
                if (messages.length === 0) return "";

                const lastMessage = messages[messages.length - 1];

                let markdown = lastMessage.querySelector('.markdown.markdown-main-panel');
                if (!markdown) markdown = lastMessage.querySelector('.markdown');

                if (markdown) {
                    const clone = markdown.cloneNode(true);
                    clone.querySelectorAll(
                        'sup, source-footnote, sources-carousel-inline, source-inline-chip, .citation-end, .superscript'
                    ).forEach(el => el.remove());
                    return clone.innerText.trim();
                }

                return lastMessage.innerText.trim();
            }
            """
        )
    
    last_text = ""
    stable_count = 0
    elapsed = 0

    while elapsed < timeout_sec:
        text = await get_last_gemini_response()
        cleaned = " ".join(text.split())

        if cleaned and cleaned != last_text:
            last_text = cleaned
            stable_count = 0
        elif cleaned and cleaned == last_text:
            stable_count += 1
            if stable_count >= stable_checks:
                return cleaned

        await page.wait_for_timeout(interval_sec * 1000)
        elapsed += interval_sec

    return last_text


def save_to_file(response_text: str, original_file_path: str):
    try:
        original_path = Path(original_file_path)
        output_filename = f"{original_path.stem}_legal_analysis.txt"
        output_path = Path("H:/Legal_text_summarizer") / output_filename

        timestamp = __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Format each section on its own block with spacing
        sections = [
            "SHORT SUMMARY",
            "ISSUE",
            "RULE",
            "ANALYSIS",
            "CONCLUSION",
            "LEGAL ADVICE"
        ]

        formatted = response_text
        for section in sections:
            formatted = formatted.replace(
                f"{section}:",
                f"\n\n{'='*60}\n{section}\n{'='*60}\n"
            )

        content = f"""LEGAL ANALYSIS SUMMARY
Generated: {timestamp}
Source Document: {original_path.name}
{'='*60}
{formatted.strip()}
"""

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"\n✅ Summary saved to: {output_path}")
        return output_path

    except Exception as e:
        print(f"\n❌ Error saving file: {e}")
        return None


def print_results(response_text: str, original_file_path: str):
    """
    Print the extracted response to terminal and save to file.
    
    Args:
        response_text: Gemini's response text
        original_file_path: Path to the original document
    """
    print("\n" + "="*80)
    print("LEGAL ANALYSIS RESULTS")
    print("="*80)
    print(response_text)
    print("="*80)
    
    # Save to file
    save_to_file(response_text, original_file_path)
    
    print("\nAnalysis complete.")


async def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description='Legal Text Summarizer - Analyze legal documents using Gemini AI')
    parser.add_argument('file_path', nargs='?', help='Path to the document file (PDF or TXT)')
    
    args = parser.parse_args()
    
    print("Legal Text Summarizer - Gemini AI Analysis")
    print("-" * 50)
    
    # Get file path from command line or user input
    if args.file_path:
        file_path = args.file_path
        print(f"Using file: {file_path}")
    else:
        file_path = input("Enter the path to your document (PDF or TXT): ").strip()
    
    if not file_path:
        print("Error: No file path provided.")
        return
    
    # Clean the file path - remove quotes and extra whitespace
    file_path = file_path.strip('"\'')  # Remove surrounding quotes
    file_path = file_path.strip()  # Remove any remaining whitespace
    
    # Step 1: Extract text
    print("\n1. Extracting text from document...")
    raw_text = extract_text(file_path)
    
    if not raw_text:
        print("Failed to extract text. Exiting.")
        return
    
    print(f"Extracted {len(raw_text)} characters.")
    
    # Step 2: Clean text
    print("\n2. Cleaning text...")
    cleaned_text = clean_text(raw_text)
    print(f"Cleaned text length: {len(cleaned_text)} characters.")
    
    # Step 3: Truncate text
    print("\n3. Truncating text to 12000 characters...")
    truncated_text = truncate_text(cleaned_text)
    print(f"Final text length: {len(truncated_text)} characters.")
    
    # Step 4: Build prompt
    print("\n4. Building prompt for Gemini...")
    prompt = build_prompt(truncated_text)
    
    # Step 5: Submit to Gemini
    print("\n5. Submitting to Gemini...")
    response = await open_gemini_and_submit(prompt)
    
    if response:
        # Step 6: Print results
        print_results(response, file_path)
    else:
        print("Failed to get response from Gemini.")
    
    print("\nPress Ctrl+C to exit when you're done reviewing the browser.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
