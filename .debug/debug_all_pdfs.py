
import os
import sys
import json
import subprocess
import glob
import random
import traceback

# Setup paths
base_dir = r"c:\DEV\IPED"
task_dir = os.path.join(base_dir, "iped-app", "resources", "scripts", "tasks")
sys.path.append(task_dir)

print(f"[SETUP] Task Dir: {task_dir}")

try:
    from FiscalDataExtractionTask import FiscalDataExtractionTask
    print("[SETUP] FiscalDataExtractionTask imported successfully.")
except ImportError as e:
    print(f"[ERROR] Failed to import FiscalDataExtractionTask: {e}")
    sys.exit(1)

# Java Compilation (if needed)
def compile_parsers():
    print("[SETUP] Compiling Java Helper & Sources...")
    cp = os.path.join(base_dir, "iped-parsers", "iped-parsers-impl", "target", "classes")
    # Add dependencies if needed (e.g. pdfbox) but usually for this simple parser just source is enough if deps are in CP
    # For simplicity, assuming the user env has what's needed or we use a pre-compiled CP.
    # Actually, we rely on iped-parsers-impl being built.
    pass

compile_parsers()

# Expected Values
expected_file = os.path.join(base_dir, ".exemplos", "expected_values.json")
expected_data = {}
if os.path.exists(expected_file):
    with open(expected_file, 'r', encoding='utf-8') as f:
        expected_data = json.load(f)
    print(f"[INFO] Loaded {len(expected_data)} expected value entries")

# Main Test Loop
task = FiscalDataExtractionTask()

def extract_from_pdf(pdf_path):
    # Call Java Parser via subprocess to get JSON items
    # We use a simple java runner that invokes PDFPositionalTextParser
    # Need to construct classpath
    
    # jars
    lib_dir = os.path.join(base_dir, "iped-app", "target", "lib") # approx
    # Actually, we need to find where the jars are.
    # Assuming standard dev structure or finding jars in .debug if we left them? 
    # Attempt to use a collected CP string or find jars.
    
    # Quick hack: use the CP known to work in previous runs if possible.
    # Or just try to run with known location.
    
    # Path to compiled classes including our PDFPositionalTextParser
    classes_dir = os.path.join(base_dir, "iped-parsers", "iped-parsers-impl", "target", "classes")
    # We also need PDFBox.
    
    # Use a helper script or command. 
    # Let's construct a command that runs the Java class directly if we can find deps.
    # If not, we might fail hard.
    
    # Check if we can find dependnecy jars in iped-app/target/iped-app-*/lib
    pass
    
    cp_elements = [classes_dir]
    
    # Robust search for lib
    possible_libs = glob.glob(os.path.join(base_dir, "target", "release", "*", "lib"))
    if not possible_libs:
         possible_libs = glob.glob(os.path.join(base_dir, "iped-app", "target", "*", "lib"))
    
    if possible_libs:
        lib_dir = possible_libs[0]
        # print(f"[DEBUG] Found lib dir: {lib_dir}")
        # Use wildcard to avoid long command line
        cp_elements.append(os.path.join(lib_dir, "*"))
    else:
        pass # print("[DEBUG] No lib dir found!")

    cp_str = ";".join(cp_elements)
    # print(f"[DEBUG] CP Elements count: {len(cp_elements)}")
    if len(cp_elements) < 5:
        pass # print(f"[DEBUG] CP: {cp_str}")
    
    cmd = [
        "java", "-cp", cp_str, 
        "iped.parsers.misc.PDFPositionalTextParser", 
        pdf_path
    ]
    
    try:
        # We need to ensure we can run this. 
        # If compilation failed or jars missing, this will fail.
        # But previous runs worked, so we hope CP is correct.
        
        # NOTE: PDFPositionalTextParser might be in src/main/java and not compiled to target/classes?
        # User might have compiled it?
        # Let's try running.
        
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            err = result.stderr.decode('utf-8', 'ignore') if result.stderr else "Unknown Error"
            # print(f"[ERROR] Java parser failed for {pdf_path}")
            # print(f"[DEBUG] CMD: {cmd}")
            # print(f"[DEBUG] STDERR: {err}")
            return None
            
        out = result.stdout.decode('utf-8', 'ignore') if result.stdout else ""
        if not out.strip():
             # print(f"[ERROR] Empty output from Java parser for {pdf_path}")
             return None
        return json.loads(out)
        
    except Exception as e:
        pass # print(f"[ERROR] Exception running java parser: {e}")
        return None

def normalize(s):
    if not s: return "MISSING"
    return str(s).strip()

def title_case(s):
    """Title case with lowercase connectors and uppercase state abbreviations."""
    if not s or s == "MISSING": return s
    connectors = {"de", "da", "do", "das", "dos", "e", "em", "para", "com", "sem", "por", "a", "o", "as", "os"}
    # Brazilian state abbreviations
    states = {"AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"}
    # Company suffixes to remove
    suffixes = {"eireli", "ltda", "ltda.", "s.a.", "sa", "s/a", "me", "epp", "ss"}
    
    words = s.split()
    # Filter out company suffixes
    words = [w for w in words if w.lower() not in suffixes]
    
    result = []
    for i, w in enumerate(words):
        lower_w = w.lower()
        upper_w = w.upper()
        # Check if it's a state abbreviation
        if upper_w in states:
            result.append(upper_w)
        elif lower_w in connectors:
            if i == 0:
                result.append(w.capitalize())
            else:
                result.append(lower_w)
        else:
            result.append(w.capitalize())
    return " ".join(result)

def compare(actual, expected_key, expected_dict, file_has_expected=False):
    exp = expected_dict.get(expected_key)
    act = actual.get(expected_key)
    
    n_exp = normalize(exp)
    n_act = normalize(act)
    
    # Apply title case (which also removes company suffixes)
    n_exp_disp = title_case(n_exp)
    n_act_disp = title_case(n_act)
    
    has_expected_for_key = (n_exp != "MISSING")
    
    # Compare using normalized display values (after suffix removal and case normalization)
    match = False
    if n_exp_disp == n_act_disp: match = True
    elif n_exp_disp != "MISSING" and n_act_disp != "MISSING":
        # Substring match (case insensitive)
        if n_exp_disp.upper() in n_act_disp.upper() or n_act_disp.upper() in n_exp_disp.upper(): match = True
        # Punctuation-stripped match (for CNPJs)
        elif n_exp.replace(".","").replace("/","").replace("-","") == n_act.replace(".","").replace("/","").replace("-",""): match = True
    
    # No truncation - show full string
    is_error = False
    if has_expected_for_key:
        if match:
            # BLUE = Match Expected
            return (f"\033[94m{n_act_disp}\033[0m", False)
        else:
            # RED = Mismatch (Show expected)
            is_error = True
            return (f"\033[91m{n_act_disp} (EXP: {n_exp_disp})\033[0m", True)
    else:
        # Key not in expected_values for this file
        if n_act != "MISSING":
            # GREEN = Extracted but no expected for this key
            if file_has_expected:
                return (f"\033[92m{n_act_disp} (EXP: N/A)\033[0m", False)
            else:
                return (f"\033[92m{n_act_disp}\033[0m", False)
        else:
            # YELLOW = Not Available (counts as error if file has expected values)
            return (f"\033[93m{n_act_disp}\033[0m", file_has_expected)

pdf_dir = os.path.join(base_dir, ".exemplos")
all_pdfs = glob.glob(os.path.join(pdf_dir, "*.pdf")) + glob.glob(os.path.join(pdf_dir, "*.PDF"))
all_pdfs = sorted(list(set(all_pdfs)))

# Priority files from expected_values.json
priority_basenames = list(expected_data.keys())
priority_pdfs = [p for p in all_pdfs if os.path.basename(p) in priority_basenames]

# Other files
other_pdfs = [p for p in all_pdfs if os.path.basename(p) not in priority_basenames]

# Parse arguments
n_extra = 0
show_errors_only = False

for arg in sys.argv[1:]:
    if arg in ['--errors', '-e']:
        show_errors_only = True
    else:
        try:
            n_extra = int(arg)
        except:
            pass

pdfs = priority_pdfs + other_pdfs[:n_extra]

# print(f"[INFO] Found {len(pdfs)} PDFs to process (Priority: {len(priority_pdfs)}, Extra: {n_extra})")

print(f"[INFO] Found {len(pdfs)} PDFs in {pdf_dir}")
print()
print("="*148)
print(f"{'FILE':<25} | {'TYPE':<5} | {'REMET CNPJ':<25} | {'REMET NAME':<25} | {'REMET LOC':<25} | {'DEST CNPJ':<25} | {'DEST NAME':<25} | {'DEST LOC':<25} | {'VALOR':<12} | {'ICMS':<10}")
print("="*148)
print("Legend: \033[94mBLUE=Matches Expected\033[0m, \033[92mGREEN=Extracted OK\033[0m, \033[91mRED=Error/Mismatch\033[0m, \033[93mYELLOW=Not Available\033[0m")
print("-" * 148)

for pdf in pdfs:
    fname = os.path.basename(pdf)
    exp = expected_data.get(fname, {})
    
    items = extract_from_pdf(pdf)
    
    res = {}
    doc_type = "UNK"
    if items:
        # Check type
        # Heuristic
        text_dump = " ".join([i.get('t','') for i in items])
        if "DANFE" in text_dump or "NOTA FISCAL" in text_dump:
            doc_type = "NFe"
        elif "DACTE" in text_dump or "CONHECIMENTO DE TRANSPORTE" in text_dump:
            doc_type = "CTe"
            
        # res = task.process(items, extract_type=doc_type) 
        # Call specific methods directly
        if doc_type == "NFe":
             res = task._extract_nfe_spatial_raw(items)
        elif doc_type == "CTe":
             res = task._extract_cte_spatial_raw(items)

    else:
        print(f"{fname:<25} | ERROR PARSING")
        continue

    # Format Output
    type_str = f"\033[94m{doc_type:<5}\033[0m"
    
    file_has_exp = bool(exp)
    
    remet_cnpj, err1 = compare(res, 'remetCNPJ', exp, file_has_exp)
    remet_name, err2 = compare(res, 'remetName', exp, file_has_exp)
    
    # Combine city - uf for display
    r_city = res.get('remetCity', '')
    r_uf = res.get('remetUF', '')
    r_full = f"{r_city} - {r_uf}" if r_city and r_uf else r_city
    res['remetCity'] = r_full  # Update with combined value for comparison
    remet_loc, err3 = compare(res, 'remetCity', exp, file_has_exp)  # Use remetCity key to match expected
    
    dest_cnpj, err4 = compare(res, 'destCNPJ', exp, file_has_exp)
    dest_name, err5 = compare(res, 'destName', exp, file_has_exp)
    
    d_city = res.get('destCity', '')
    d_uf = res.get('destUF', '')
    d_full = f"{d_city} - {d_uf}" if d_city and d_uf else d_city
    res['destCity'] = d_full  # Update with combined value for comparison
    dest_loc, err6 = compare(res, 'destCity', exp, file_has_exp)  # Use destCity key to match expected
    
    val, err7 = compare(res, 'value', exp, file_has_exp)
    icms, err8 = compare(res, 'icms', exp, file_has_exp)
    
    has_error = any([err1, err2, err3, err4, err5, err6, err7, err8])
    
    if show_errors_only and not has_error:
        continue
    
    print(f"{fname:<25} | {type_str} | {remet_cnpj} | {remet_name} | {remet_loc} | {dest_cnpj} | {dest_name} | {dest_loc} | {val} | {icms}")

print("="*148)
print()
