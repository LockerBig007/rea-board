// Доска дедлайнов хранится в Supabase. Пока адрес проекта не вписан, страница
// работает как справочник: расписание, калькулятор, контрольные точки и кисть
// на месте, а блок «Доска группы» сообщает, что его ещё не подключили.
//
// Где взять значения: supabase.com -> проект -> Project Settings -> API.
// supabaseUrl  — поле «Project URL», вида https://xxxxxxxx.supabase.co
// supabaseAnonKey — публичный ключ: новый формат начинается с sb_publishable_,
//   старый — с eyJ (он же anon public). Годится любой из двух.
//
// Этот ключ публичный по назначению и должен лежать в коде страницы.
// Ключ sb_secret_ (он же service_role) сюда класть нельзя никогда.
//
// Таблицу и права создаёт supabase.sql — выполните его в SQL Editor до того,
// как открывать доску.

window.REA_CONFIG = {
  supabaseUrl: "https://ernanilptsyylgjqlwnz.supabase.co",
  supabaseAnonKey: "sb_publishable_4zeLZn7KHPrib93vguLTuQ_-qWfvJbz"
};
