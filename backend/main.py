#!/usr/bin/env python3
"""
FastAPI Backend for Legal Text Summarizer
Provides API endpoints for document analysis using Gemini AI
"""

import os
import re
import asyncio
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any

import PyPDF2
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from pydantic import BaseModel

app = FastAPI(title="Legal Text Summarizer API", version="1.0.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store for analysis results (in production, use a proper database)
analysis_results: Dict[str, Dict[str, Any]] = {}

class AnalysisResponse(BaseModel):
    task_id: str
    status: str
    message: str
    result: Optional[str] = None

class AnalysisStatus(BaseModel):
    task_id: str
    status: str
    message: str
    result: Optional[str] = None
    download_url: Optional[str] = None

def extract_text_from_pdf(file_path: Path) -> str:
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
        raise HTTPException(status_code=500, detail=f"Error reading PDF: {e}")

def extract_text_from_txt(file_path: Path) -> str:
    """Extract text from TXT file."""
    try:
        encodings = ['utf-8', 'utf-16', 'latin-1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as file:
                    return file.read()
            except UnicodeDecodeError:
                continue
                
        raise HTTPException(status_code=500, detail="Could not decode text file with any supported encoding")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading text file: {e}")

def clean_text(text: str) -> str:
    """Clean extracted text by removing page numbers and excessive whitespace."""
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
    """Truncate text to maximum character limit."""
    if len(text) <= max_chars:
        return text
    
    # Truncate at word boundary if possible
    truncated = text[:max_chars]
    last_space = truncated.rfind(' ')
    
    if last_space > max_chars * 0.9:  # If we're close to the limit, use word boundary
        truncated = truncated[:last_space]
    
    return truncated + "\n\n[Note: Document was truncated to fit character limit]"

def build_prompt(case_text: str) -> str:
    """Build the combined prompt for Gemini AI."""
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

async def analyze_with_gemini(prompt_text: str) -> str:
    """Analyze text using Gemini AI via Playwright."""
    playwright = await async_playwright().start()
    
    try:
        # Launch browser
        browser = await playwright.chromium.launch(
            headless=True,  # Run headless for API
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        
        # Create context
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
                break
            except PlaywrightTimeoutError:
                continue
        
        if not input_element:
            # Check if login is required
            body_text = (await page.locator("body").inner_text()).lower()
            if any(marker in body_text for marker in ["sign in", "log in", "to continue to gemini"]):
                raise HTTPException(status_code=401, detail="Gemini login required. Please log in to Google in your browser.")
            else:
                raise HTTPException(status_code=500, detail="Could not find input field on Gemini page")
        
        # Input the prompt
        await input_element.click(force=True)
        
        try:
            await input_element.fill(prompt_text)
        except Exception:
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.keyboard.type(prompt_text, delay=15)
        
        await page.keyboard.press("Enter")
        
        # Wait for response
        response = await wait_for_stable_answer(page)
        
        return response
        
    except Exception as e:
        if "login" in str(e).lower():
            raise HTTPException(status_code=401, detail="Gemini login required. Please log in to Google in your browser.")
        raise HTTPException(status_code=500, detail=f"Error analyzing with Gemini: {e}")
    finally:
        await playwright.stop()

async def wait_for_stable_answer(page, timeout_sec: int = 180, stable_checks: int = 3, interval_sec: int = 2) -> str:
    """Wait for Gemini to finish generating a stable response."""
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

def save_analysis_to_file(response_text: str, original_filename: str) -> str:
    """Save analysis to file and return the file path."""
    try:
        # Create output filename
        original_path = Path(original_filename)
        output_filename = f"{original_path.stem}_legal_analysis.txt"
        output_path = Path("outputs") / output_filename
        
        # Create outputs directory if it doesn't exist
        output_path.parent.mkdir(exist_ok=True)
        
        # Format response
        timestamp = __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
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
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return str(output_path)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving analysis: {e}")

async def process_document(task_id: str, file_path: str, filename: str):
    """Background task to process document and generate analysis."""
    try:
        # Update status
        analysis_results[task_id] = {
            "status": "processing",
            "message": "Extracting text from document...",
            "result": None,
            "download_url": None
        }
        
        # Extract text
        file_path_obj = Path(file_path)
        if file_path_obj.suffix.lower() == '.pdf':
            raw_text = extract_text_from_pdf(file_path_obj)
        elif file_path_obj.suffix.lower() == '.txt':
            raw_text = extract_text_from_txt(file_path_obj)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type. Only PDF and TXT files are supported.")
        
        # Update status
        analysis_results[task_id]["message"] = "Cleaning and processing text..."
        
        # Clean and truncate text
        cleaned_text = clean_text(raw_text)
        truncated_text = truncate_text(cleaned_text)
        
        # Update status
        analysis_results[task_id]["message"] = "Building prompt for Gemini..."
        
        # Build prompt
        prompt = build_prompt(truncated_text)
        
        # Update status
        analysis_results[task_id]["message"] = "Analyzing with Gemini AI..."
        
        # Analyze with Gemini
        response = await analyze_with_gemini(prompt)
        
        # Update status
        analysis_results[task_id]["message"] = "Saving analysis..."
        
        # Save to file
        output_path = save_analysis_to_file(response, filename)
        
        # Update final status
        analysis_results[task_id] = {
            "status": "completed",
            "message": "Analysis completed successfully",
            "result": response,
            "download_url": f"/download/{task_id}",
            "output_path": output_path,
            "original_filename": filename
        }
        
    except Exception as e:
        analysis_results[task_id] = {
            "status": "failed",
            "message": f"Error: {str(e)}",
            "result": None,
            "download_url": None
        }

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Legal Text Summarizer API", "version": "1.0.0"}

@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_document(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Upload and analyze a legal document"""
    
    # Validate file type
    if not file.filename.lower().endswith(('.pdf', '.txt')):
        raise HTTPException(status_code=400, detail="Only PDF and TXT files are supported")
    
    # Generate task ID
    import uuid
    task_id = str(uuid.uuid4())
    
    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_file_path = tmp_file.name
    
    # Initialize task status
    analysis_results[task_id] = {
        "status": "queued",
        "message": "Document uploaded, starting analysis...",
        "result": None,
        "download_url": None
    }
    
    # Start background processing
    background_tasks.add_task(process_document, task_id, tmp_file_path, file.filename)
    
    return AnalysisResponse(
        task_id=task_id,
        status="queued",
        message="Document uploaded successfully. Analysis started."
    )

@app.get("/status/{task_id}", response_model=AnalysisStatus)
async def get_analysis_status(task_id: str):
    """Get the status of an analysis task"""
    
    if task_id not in analysis_results:
        raise HTTPException(status_code=404, detail="Task not found")
    
    result = analysis_results[task_id]
    
    return AnalysisStatus(
        task_id=task_id,
        status=result["status"],
        message=result["message"],
        result=result.get("result"),
        download_url=result.get("download_url")
    )

@app.get("/download/{task_id}")
async def download_analysis(task_id: str):
    """Download the analysis result as a text file"""
    
    if task_id not in analysis_results:
        raise HTTPException(status_code=404, detail="Task not found")
    
    result = analysis_results[task_id]
    
    if result["status"] != "completed":
        raise HTTPException(status_code=400, detail="Analysis not completed yet")
    
    # Use the stored file path and original filename
    output_path = result.get("output_path")
    original_filename = result.get("original_filename", "document")
    
    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=404, detail="Analysis file not found")
    
    # Generate proper download filename
    download_filename = f"{Path(original_filename).stem}_legal_analysis.txt"
    
    return FileResponse(
        path=output_path,
        filename=download_filename,
        media_type="text/plain"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
