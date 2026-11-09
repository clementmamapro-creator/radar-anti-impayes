-- Espace client Acquit (V0, semaine 1) : profil de l'entreprise.
-- À exécuter une fois dans Supabase › SQL Editor.
-- Principe : chaque client ne voit et ne modifie que SA ligne (Row Level Security).

create table if not exists public.entreprises (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null unique references auth.users (id) on delete cascade,
  nom           text not null check (char_length(nom) between 1 and 120),
  metier        text not null check (char_length(metier) between 1 and 120),
  ville         text check (char_length(ville) <= 120),
  departement   text not null check (departement ~ '^(\d{2}|2A|2B|97\d)$'),
  rayon_km      smallint not null default 15 check (rayon_km between 1 and 200),
  ton           text not null default 'cordial' check (ton in ('cordial', 'direct', 'chaleureux')),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

comment on table public.entreprises is 'Profil de l''entreprise cliente (une ligne par compte).';

-- Mise à jour automatique de updated_at
create or replace function public.touch_updated_at() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  return new;
end $$;

drop trigger if exists entreprises_updated_at on public.entreprises;
create trigger entreprises_updated_at before update on public.entreprises
  for each row execute function public.touch_updated_at();

-- Sécurité : RLS activée, accès limité au propriétaire de la ligne
alter table public.entreprises enable row level security;

drop policy if exists "lire son entreprise" on public.entreprises;
create policy "lire son entreprise" on public.entreprises
  for select to authenticated using ((select auth.uid()) = user_id);

drop policy if exists "créer son entreprise" on public.entreprises;
create policy "créer son entreprise" on public.entreprises
  for insert to authenticated with check ((select auth.uid()) = user_id);

drop policy if exists "modifier son entreprise" on public.entreprises;
create policy "modifier son entreprise" on public.entreprises
  for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

-- Les nouvelles tables ne sont pas exposées automatiquement (choix fait à la création du projet) :
-- on ouvre explicitement cette table aux utilisateurs connectés, jamais aux anonymes.
revoke all on public.entreprises from anon;
grant select, insert, update on public.entreprises to authenticated;
