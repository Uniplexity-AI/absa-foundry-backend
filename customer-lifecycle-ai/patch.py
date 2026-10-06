import re

with open('gateway/routes/etl_routes.py', 'r', encoding='utf-8') as f:
    code = f.read()

target = '''            if body.sync:
                subprocess.run(cmd, stdout=log_file, stderr=subprocess.STDOUT, cwd=str(_RUN_ETL.parent), check=True)
            else:
                subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, cwd=str(_RUN_ETL.parent))'''

replacement = '''            if body.sync:
                subprocess.run(cmd, stdout=log_file, stderr=subprocess.STDOUT, cwd=str(_RUN_ETL.parent), check=True)
                if body.run_models:
                    models_cmd = [sys.executable, str(_RUN_ETL), "--models", body.run_models]
                    if body.snapshot:
                        models_cmd.extend(["--snapshot", body.snapshot])
                    if body.force:
                        models_cmd.append("--force")
                    subprocess.run(models_cmd, stdout=log_file, stderr=subprocess.STDOUT, cwd=str(_RUN_ETL.parent), check=True)
            else:
                subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, cwd=str(_RUN_ETL.parent))'''

code = code.replace(target, replacement)

with open('gateway/routes/etl_routes.py', 'w', encoding='utf-8') as f:
    f.write(code)

