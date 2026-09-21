
ALTER TABLE public.customers_clean ADD COLUMN IF NOT EXISTS next_of_kin_name VARCHAR(128);
ALTER TABLE public.customers_clean ADD COLUMN IF NOT EXISTS next_of_kin_relationship VARCHAR(64);
ALTER TABLE public.customers_clean ADD COLUMN IF NOT EXISTS next_of_kin_phone VARCHAR(32);
