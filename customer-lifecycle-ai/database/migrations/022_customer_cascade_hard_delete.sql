-- Migration 022: Configure ON DELETE CASCADE on clean tables referencing customers_clean
-- Allows permanent/hard deletion of customer records across the clean data layer.

ALTER TABLE public.customer_transactions_clean
  DROP CONSTRAINT IF EXISTS customer_transactions_clean_customer_id_fkey;

ALTER TABLE public.customer_transactions_clean
  ADD CONSTRAINT customer_transactions_clean_customer_id_fkey
  FOREIGN KEY (customer_id) REFERENCES public.customers_clean(customer_id)
  ON DELETE CASCADE;

ALTER TABLE public.accounts_clean
  DROP CONSTRAINT IF EXISTS accounts_clean_customer_id_fkey;

ALTER TABLE public.accounts_clean
  ADD CONSTRAINT accounts_clean_customer_id_fkey
  FOREIGN KEY (customer_id) REFERENCES public.customers_clean(customer_id)
  ON DELETE CASCADE;

ALTER TABLE public.loans_clean
  DROP CONSTRAINT IF EXISTS loans_clean_customer_id_fkey;

ALTER TABLE public.loans_clean
  ADD CONSTRAINT loans_clean_customer_id_fkey
  FOREIGN KEY (customer_id) REFERENCES public.customers_clean(customer_id)
  ON DELETE CASCADE;

ALTER TABLE public.cards_clean
  DROP CONSTRAINT IF EXISTS cards_clean_customer_id_fkey;

ALTER TABLE public.cards_clean
  ADD CONSTRAINT cards_clean_customer_id_fkey
  FOREIGN KEY (customer_id) REFERENCES public.customers_clean(customer_id)
  ON DELETE CASCADE;

ALTER TABLE public.digital_engagement_clean
  DROP CONSTRAINT IF EXISTS digital_engagement_clean_customer_id_fkey;

ALTER TABLE public.digital_engagement_clean
  ADD CONSTRAINT digital_engagement_clean_customer_id_fkey
  FOREIGN KEY (customer_id) REFERENCES public.customers_clean(customer_id)
  ON DELETE CASCADE;

ALTER TABLE public.demographics_clean
  DROP CONSTRAINT IF EXISTS demographics_clean_customer_id_fkey;

ALTER TABLE public.demographics_clean
  ADD CONSTRAINT demographics_clean_customer_id_fkey
  FOREIGN KEY (customer_id) REFERENCES public.customers_clean(customer_id)
  ON DELETE CASCADE;
