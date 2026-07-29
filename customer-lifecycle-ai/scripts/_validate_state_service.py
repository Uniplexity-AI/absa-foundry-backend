"""Validation script — checks all Customer State Service files import."""
import sys, os
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)
sys.path.insert(0, os.path.join(_project_root, 'services', 'customer-state-service'))

errors = 0

def check(name, module_path):
    global errors
    try:
        __import__(module_path)
        print(f'  {name}: OK')
    except Exception as e:
        print(f'  {name}: FAILED — {e}')
        errors += 1

check('config/settings', 'app.config.settings')
check('schemas/state', 'app.schemas.state')
check('schemas/transition', 'app.schemas.transition')
check('repository/state_repository', 'app.repository.state_repository')
check('repository/journey_repository', 'app.repository.journey_repository')
check('services/state_engine', 'app.services.state_engine')
check('services/state_service', 'app.services.state_service')
check('services/transition_analyzer', 'app.services.transition_analyzer')
check('services/journey_analyzer', 'app.services.journey_analyzer')
check('engines/markov/engine', 'app.engines.markov.engine')

# Syntax check non-importable files
import ast
try:
    ast.parse(open('gateway/app/routes/customer_state.py').read())
    print('  gateway/routes/customer_state.py: OK')
except Exception as e:
    print(f'  gateway/routes/customer_state.py: FAILED — {e}')
    errors += 1

try:
    ast.parse(open('scripts/seed_states.py').read())
    print('  scripts/seed_states.py: OK')
except Exception as e:
    print(f'  scripts/seed_states.py: FAILED — {e}')
    errors += 1

print()
if errors:
    print(f'{errors} FILE(S) FAILED')
else:
    print('ALL 13 FILES VALIDATED')
