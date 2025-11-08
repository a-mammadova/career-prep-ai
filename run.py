import os
import sys
from pathlib import Path
from typing import Optional
import pdfplumber
import openai
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

def ensure_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

def extract_text_from_pdf(pdf_path: Path) -> str:
    collected_text = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                collected_text.append(page_text)
    return "\n\n".join(collected_text).strip()

def generate_questions_answers_with_openai(jd_text: str, num_questions: int, experience_level: str) -> str:
    api_key = ""
    client = openai.OpenAI(api_key=api_key)

    level_descriptions = {
        "entry": "entry-level or junior position (0-2 years experience)",
        "mid": "mid-level position (2-5 years experience)", 
        "senior": "senior or advanced position (5+ years experience)",
        "executive": "executive or leadership position"
    }
    
    level_description = level_descriptions.get(experience_level, "professional position")

    system_prompt = f"""You are an expert interviewer and hiring manager. Generate {num_questions} interview questions with detailed, professional answers tailored for a {level_description}. 
    
For each question, provide:
1. The interview question
2. A comprehensive ideal answer that demonstrates expertise
3. Key points the candidate should cover

Format each as:
Question: [question]
Answer: [detailed answer]"""

    user_prompt = f"""Based on this job description, generate exactly {num_questions} interview questions with ideal candidate answers for a {level_description}:

{jd_text}

Make the questions relevant to the experience level and provide comprehensive answers that would impress interviewers."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=2500, 
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error generating questions: {str(e)}"

def analyze_skill_gap_with_openai(jd_text: str, cv_text: str) -> str:
    api_key = "-"
    client = openai.OpenAI(api_key=api_key)

    system_prompt = """You are an expert career coach and recruiter. Analyze the skill gap between a candidate's CV and a job description. Provide a comprehensive skill gap analysis with:

1. STRENGTHS: Skills and experiences that match well
2. GAPS: Missing skills or experience requirements  
3. RECOMMENDATIONS: How to bridge the gaps
4. PREPARATION TIPS: Specific areas to focus on for the interview

Format the analysis clearly with sections and bullet points."""

    user_prompt = f"""JOB DESCRIPTION:
{jd_text}

CANDIDATE CV:
{cv_text}

Please provide a detailed skill gap analysis between the candidate's qualifications and the job requirements."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=3000,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error analyzing skill gap: {str(e)}"

def write_text_pdf(text: str, output_pdf: Path, title: str, subtitle: str = "") -> None:
    ensure_output_dir(output_pdf.parent)
    
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    with open(os.devnull, 'w') as f:
        sys.stdout = f
        sys.stderr = f
        
        try:
            c = canvas.Canvas(str(output_pdf), pagesize=LETTER)
            width, height = LETTER

            font_name = "Helvetica"
            left_margin = 1 * inch
            right_margin = 1 * inch
            top_margin = 1 * inch
            bottom_margin = 1 * inch
            usable_width = width - left_margin - right_margin

            font_size = 11
            line_height = 14
            
            # Enhanced header with title and subtitle
            c.setFont("Helvetica-Bold", 16)
            c.drawString(left_margin, height - top_margin, title)
            
            y = height - top_margin - 25
            
            if subtitle:
                c.setFont("Helvetica", 12)
                c.drawString(left_margin, y, subtitle)
                y -= 20
            
            # Add separator line
            c.line(left_margin, y, width - right_margin, y)
            y -= 30
            
            c.setFont(font_name, font_size)

            def wrap_line(input_line: str) -> list[str]:
                words = input_line.split(" ")
                wrapped = []
                current = ""
                for word in words:
                    trial = word if not current else current + " " + word
                    if pdfmetrics.stringWidth(trial, font_name, font_size) <= usable_width:
                        current = trial
                    else:
                        if current:
                            wrapped.append(current)
                        current = word
                if current:
                    wrapped.append(current)
                return wrapped

            x = left_margin

            for raw_line in text.splitlines():
                if y - line_height < bottom_margin:
                    c.showPage()
                    c.setFont(font_name, font_size)
                    y = height - top_margin - 30

                if not raw_line.strip():
                    y -= line_height  
                    continue

                for line in wrap_line(raw_line):
                    if y - line_height < bottom_margin:
                        c.showPage()
                        c.setFont(font_name, font_size)
                        y = height - top_margin - 30
                    c.drawString(x, y, line)
                    y -= line_height

            c.save()
            
        except Exception as e:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            raise e
    
    sys.stdout = original_stdout
    sys.stderr = original_stderr

def run():
    # Get both input files
    job_pdf = Path("job_pdf.pdf")
    cv_pdf = Path("cv_pdf.pdf")

    # Checkbox handling - Abyss returns JSON array
    selected_outputs_str = os.environ.get('output_selection', '').strip()
    
    # Debug: see what we're getting from the checkbox
    print(f"DEBUG: Selected outputs string: '{selected_outputs_str}'", file=sys.stderr)
    
    # Parse JSON array instead of comma-separated string
    import json
    try:
        if selected_outputs_str:
            selected_outputs = json.loads(selected_outputs_str)
        else:
            selected_outputs = []
    except json.JSONDecodeError:
        # Fallback: try comma-separated if JSON fails
        selected_outputs = [item.strip() for item in selected_outputs_str.split(',')] if selected_outputs_str else []
    
    # Debug: show parsed outputs
    print(f"DEBUG: Parsed outputs: {selected_outputs}", file=sys.stderr)
    
    # Convert to boolean flags - using the actual option names
    generate_qa = 'Interview Q&A' in selected_outputs
    generate_skill_gap = 'Skill Gap Report' in selected_outputs  # Changed to match your option name
    
    # Debug: show what we're generating
    print(f"DEBUG: Generate QA: {generate_qa}, Generate Skill Gap: {generate_skill_gap}", file=sys.stderr)

    # Validate file requirements
    if not job_pdf.exists():
        ensure_output_dir(Path('output'))
        with open('output/error.txt', 'w') as f:
            f.write("Please upload a Job Description PDF file.")
        return
        
    if generate_skill_gap and not cv_pdf.exists():
        ensure_output_dir(Path('output'))
        with open('output/error.txt', 'w') as f:
            f.write("Skill Gap Analysis requires a CV PDF file.")
        return

    # Get user preferences
    try:
        num_questions = int(os.environ.get('num_questions', '8'))
        num_questions = max(5, min(10, num_questions))
    except:
        num_questions = 8 

    experience_level = os.environ.get('experience_level', 'mid')
    valid_levels = ['entry', 'mid', 'senior', 'executive']
    if experience_level not in valid_levels:
        experience_level = 'mid'  

    try:
        ensure_output_dir(Path('output'))
        
        # Extract text from job description (always needed for both)
        jd_text = extract_text_from_pdf(job_pdf)
        
        # Generate outputs based on user selection
        level_display_names = {
            "entry": "Entry Level",
            "mid": "Mid Level", 
            "senior": "Senior Level",
            "executive": "Executive Level"
        }
        
        if generate_qa:
            print("🤖 Generating interview questions...", file=sys.stderr)
            qa_text = generate_questions_answers_with_openai(jd_text, num_questions, experience_level)
            write_text_pdf(
                qa_text, 
                Path("output/interview_questions.pdf"), 
                "Interview Preparation Guide",
                f"{num_questions} Questions - {level_display_names.get(experience_level, experience_level.title())} Position"
            )
            print("✅ Interview questions generated!", file=sys.stderr)
        
        if generate_skill_gap:
            print("📊 Analyzing skill gap...", file=sys.stderr)
            cv_text = extract_text_from_pdf(cv_pdf)
            skill_gap_analysis = analyze_skill_gap_with_openai(jd_text, cv_text)
            write_text_pdf(
                skill_gap_analysis,
                Path("output/skill_gap_analysis.pdf"),
                "Skill Gap Analysis Report", 
                "Candidate vs Job Requirements"
            )
            print("✅ Skill gap analysis completed!", file=sys.stderr)
        
        # Final success message
        if generate_qa and generate_skill_gap:
            print("🎉 Both reports generated successfully!", file=sys.stderr)
        elif generate_qa:
            print("🎉 Interview questions generated successfully!", file=sys.stderr)
        elif generate_skill_gap:
            print("🎉 Skill gap analysis generated successfully!", file=sys.stderr)
        else:
            print("ℹ️ No outputs selected.", file=sys.stderr)
        
    except Exception as e:
        ensure_output_dir(Path('output'))
        with open('output/error.txt', 'w') as f:
            f.write("An error occurred while processing your files. Please try again.")
if __name__ == "__main__":
    run()