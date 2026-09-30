-- Доска дедлайнов группы 15.27Д-С01/25б.
-- Выполнить один раз: supabase.com → проект → SQL Editor → New query → вставить → Run.

create table if not exists deadlines (
  id         uuid primary key default gen_random_uuid(),
  text       text        not null check (char_length(text) between 1 and 160),
  subject    smallint,                          -- индекс предмета из data.js, -1 = без предмета
  due        date,
  done       boolean     not null default false,
  author     text        not null check (char_length(author) <= 40),
  created_at timestamptz not null default now()
);

create index if not exists deadlines_created_at_idx on deadlines (created_at desc);

alter table deadlines enable row level security;

-- Страница ходит в базу публичным ключом anon: отдельных логинов у одногруппников нет.
-- Поэтому читать, добавлять и отмечать сделанным может любой, кто открыл сайт.
-- Удалять — тоже любой, но кнопка удаления в интерфейсе показывается только автору
-- записи (автор опознаётся по случайному коду в браузере). Если доску засорят,
-- откройте Table Editor и почистите руками.

drop policy if exists deadlines_read   on deadlines;
drop policy if exists deadlines_insert on deadlines;
drop policy if exists deadlines_update on deadlines;
drop policy if exists deadlines_delete on deadlines;

create policy deadlines_read   on deadlines for select using (true);
create policy deadlines_insert on deadlines for insert with check (true);
create policy deadlines_update on deadlines for update using (true) with check (true);
create policy deadlines_delete on deadlines for delete using (true);

-- Автоудаление старых закрытых записей, чтобы доска не росла бесконечно.
-- Необязательно; включите, если понадобится:
-- delete from deadlines where done and created_at < now() - interval '90 days';
