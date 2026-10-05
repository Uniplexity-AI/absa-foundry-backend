from pydantic import BaseModel, ValidationError

class M(BaseModel):
    length_years: str

try:
    M.model_validate({'length_years': None})
except ValidationError as e:
    print("When None is passed:", e.errors()[0]['msg'])

try:
    M.model_validate({'length_years': 12})
    print("When 12 is passed: success")
except ValidationError as e:
    print("When 12 is passed:", e.errors()[0]['msg'])
