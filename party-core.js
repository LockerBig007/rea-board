/* Общий движок для party.html (телефоны зала) и party-control.html (пульт).
 *
 * Связь — Supabase Realtime broadcast: события летят между открытыми
 * страницами напрямую, в базу ничего не пишется и таблицы не нужны.
 *
 * Звуки не скачиваются, а синтезируются в Web Audio. Так хор телефонов
 * звучит слитно: нечему грузиться и нечему опоздать.
 */

(function () {
  "use strict";

  var cfg = window.REA_CONFIG || {};

  /* ------------------------------------------------------------------ звук */

  var ac = null;

  function ctx() {
    if (!ac) {
      var AC = window.AudioContext || window.webkitAudioContext;
      ac = new AC();
    }
    return ac;
  }

  // Браузер не даёт играть звук, пока человек не коснулся экрана. Поэтому в
  // приложении есть кнопка «Я в игре»: её нажатие и разблокирует контекст.
  // Немой буфер обязателен — без него iOS считает контекст всё ещё спящим.
  function unlock() {
    var a = ctx();
    var done = a.state === "suspended" ? a.resume() : Promise.resolve();
    return done.then(function () {
      var b = a.createBuffer(1, 1, a.sampleRate);
      var s = a.createBufferSource();
      s.buffer = b;
      s.connect(a.destination);
      s.start(0);
      return a.state === "running";
    });
  }

  function noise(a, seconds) {
    var len = Math.max(1, Math.floor(a.sampleRate * seconds));
    var buf = a.createBuffer(1, len, a.sampleRate);
    var d = buf.getChannelData(0);
    for (var i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    var src = a.createBufferSource();
    src.buffer = buf;
    return src;
  }

  function envelope(a, t, attack, decay, peak) {
    var g = a.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(peak, t + attack);
    g.gain.exponentialRampToValueAtTime(0.0001, t + attack + decay);
    return g;
  }

  function tone(a, t, type, from, to, dur, peak, dest) {
    var o = a.createOscillator();
    o.type = type;
    o.frequency.setValueAtTime(from, t);
    if (to !== from) o.frequency.exponentialRampToValueAtTime(Math.max(1, to), t + dur);
    var g = envelope(a, t, 0.005, dur, peak);
    o.connect(g).connect(dest);
    o.start(t);
    o.stop(t + dur + 0.05);
  }

  function hit(a, t, dur, peak, filterType, freq, dest) {
    var n = noise(a, dur + 0.05);
    var f = a.createBiquadFilter();
    f.type = filterType;
    f.frequency.setValueAtTime(freq, t);
    var g = envelope(a, t, 0.002, dur, peak);
    n.connect(f).connect(g).connect(dest);
    n.start(t);
    n.stop(t + dur + 0.05);
  }

  var VOICES = {
    boom: function (a, t, out) {
      tone(a, t, "sine", 170, 32, 0.75, 1.0, out);
      tone(a, t, "triangle", 90, 28, 0.5, 0.5, out);
      hit(a, t, 0.3, 0.55, "lowpass", 900, out);
    },

    fanfare: function (a, t, out) {
      var notes = [523.25, 659.25, 783.99, 1046.5];
      for (var i = 0; i < notes.length; i++) {
        var at = t + i * 0.13;
        var dur = i === notes.length - 1 ? 0.7 : 0.16;
        tone(a, at, "square", notes[i], notes[i], dur, 0.22, out);
        tone(a, at, "sawtooth", notes[i] * 2.01, notes[i] * 2.01, dur, 0.07, out);
      }
    },

    siren: function (a, t, out) {
      var o = a.createOscillator();
      o.type = "sine";
      o.frequency.setValueAtTime(460, t);
      o.frequency.linearRampToValueAtTime(1150, t + 0.55);
      o.frequency.linearRampToValueAtTime(460, t + 1.1);
      o.frequency.linearRampToValueAtTime(1150, t + 1.65);
      var g = envelope(a, t, 0.04, 1.8, 0.3);
      o.connect(g).connect(out);
      o.start(t);
      o.stop(t + 1.9);
    },

    applause: function (a, t, out) {
      var dur = 2.4;
      var n = noise(a, dur);
      var f = a.createBiquadFilter();
      f.type = "bandpass";
      f.frequency.value = 1600;
      f.Q.value = 0.8;
      var g = a.createGain();
      g.gain.setValueAtTime(0.0001, t);
      // Хлопки — это шум с рваной громкостью: рисуем её шагами по 25 мс.
      for (var x = 0; x < dur; x += 0.025) {
        var swell = x < 0.25 ? x / 0.25 : x > dur - 0.7 ? (dur - x) / 0.7 : 1;
        g.gain.linearRampToValueAtTime(0.1 + Math.random() * 0.4 * swell, t + x);
      }
      g.gain.linearRampToValueAtTime(0.0001, t + dur);
      n.connect(f).connect(g).connect(out);
      n.start(t);
      n.stop(t + dur);
    },

    laser: function (a, t, out) {
      tone(a, t, "sawtooth", 1500, 110, 0.38, 0.3, out);
    },

    drumroll: function (a, t, out) {
      var at = t;
      var gap = 0.085;
      for (var i = 0; i < 30; i++) {
        hit(a, at, 0.05, 0.25, "bandpass", 2200, out);
        at += gap;
        gap = Math.max(0.028, gap * 0.955);
      }
      hit(a, at + 0.05, 1.1, 0.5, "highpass", 2500, out);
      tone(a, at + 0.05, "sine", 150, 40, 0.6, 0.7, out);
    },

    alarm: function (a, t, out) {
      for (var i = 0; i < 8; i++) {
        tone(a, t + i * 0.16, "square", i % 2 ? 660 : 990, i % 2 ? 660 : 990, 0.13, 0.2, out);
      }
    },

    tick: function (a, t, out) {
      hit(a, t, 0.03, 0.4, "highpass", 3500, out);
    },

    tada: function (a, t, out) {
      VOICES.fanfare(a, t, out);
      VOICES.applause(a, t + 0.55, out);
    }
  };

  var SOUNDS = [
    { id: "boom", label: "БАБАХ" },
    { id: "fanfare", label: "Фанфары" },
    { id: "tada", label: "Та-дам" },
    { id: "applause", label: "Аплодисменты" },
    { id: "drumroll", label: "Барабанная дробь" },
    { id: "siren", label: "Сирена" },
    { id: "laser", label: "Лазер" },
    { id: "alarm", label: "Тревога" },
    { id: "tick", label: "Щелчок" }
  ];

  // atMs — момент по локальным часам, когда звук должен начаться.
  function play(id, atMs) {
    var voice = VOICES[id];
    if (!voice) return false;
    var a = ctx();
    if (a.state !== "running") return false;
    var delay = atMs ? (atMs - Date.now()) / 1000 : 0;
    if (!(delay > 0) || delay > 4) delay = 0; // часы врут — играем сразу
    voice(a, a.currentTime + delay + 0.03, a.destination);
    return true;
  }

  /* ------------------------------------------------------------------ цвета */

  var COLORS = [
    { id: "red", label: "Красный", css: "#ff2d4b" },
    { id: "orange", label: "Оранжевый", css: "#ff7a18" },
    { id: "yellow", label: "Жёлтый", css: "#ffd500" },
    { id: "green", label: "Зелёный", css: "#19e68c" },
    { id: "cyan", label: "Бирюзовый", css: "#00d9ff" },
    { id: "blue", label: "Синий", css: "#2b5bff" },
    { id: "violet", label: "Фиолетовый", css: "#9b2bff" },
    { id: "pink", label: "Розовый", css: "#ff35c8" },
    { id: "white", label: "Белый", css: "#ffffff" },
    { id: "black", label: "Погасить", css: "#000000" }
  ];

  /* ------------------------------------------------------------------ связь */

  function room() {
    var m = /[?&]room=([A-Za-z0-9_-]{1,32})/.exec(location.search);
    return m ? m[1] : "rea";
  }

  function randomId() {
    return Math.random().toString(36).slice(2, 10);
  }

  /* opts: { role: "phone" | "control", name, onFx, onPeers, onStatus } */
  function connect(opts) {
    if (!cfg.supabaseUrl || !cfg.supabaseAnonKey) {
      opts.onStatus && opts.onStatus("no-config");
      return null;
    }

    var client = window.supabase.createClient(cfg.supabaseUrl, cfg.supabaseAnonKey, {
      realtime: { params: { eventsPerSecond: 40 } }
    });

    var me = randomId();
    var joined = Date.now();
    var offset = null; // часы пульта минус мои часы, по лучшей выборке
    var ch = client.channel("party:" + room(), {
      config: { broadcast: { self: false }, presence: { key: me } }
    });

    ch.on("broadcast", { event: "fx" }, function (msg) {
      var p = msg.payload || {};
      // at задан по часам пульта — переводим в свои.
      p.localAt = p.at && offset !== null ? p.at - offset : Date.now();
      opts.onFx && opts.onFx(p);
    });

    // Часы телефонов расходятся, иногда на секунды. Пульт раз в пару секунд
    // присылает своё время; лучшая (наибольшая) выборка — та, что пришла
    // быстрее всех, по ней и считаем сдвиг.
    ch.on("broadcast", { event: "clock" }, function (msg) {
      var sample = msg.payload.t - Date.now();
      if (offset === null || sample > offset) offset = sample;
    });

    ch.on("presence", { event: "sync" }, function () {
      var state = ch.presenceState();
      var phones = [];
      Object.keys(state).forEach(function (key) {
        var entry = state[key][0] || {};
        if (entry.role === "phone") {
          phones.push({ id: key, name: entry.name, joined: entry.joined || 0 });
        }
      });
      phones.sort(function (a, b) {
        return a.joined - b.joined || (a.id < b.id ? -1 : 1);
      });
      var slot = -1;
      for (var i = 0; i < phones.length; i++) if (phones[i].id === me) slot = i;
      opts.onPeers && opts.onPeers({ phones: phones, slot: slot, total: phones.length });
    });

    ch.subscribe(function (status) {
      opts.onStatus && opts.onStatus(status === "SUBSCRIBED" ? "online" : status.toLowerCase());
      if (status === "SUBSCRIBED") {
        ch.track({ role: opts.role, name: opts.name || "гость", joined: joined });
      }
    });

    return {
      id: me,
      send: function (payload) {
        ch.send({ type: "broadcast", event: "fx", payload: payload });
      },
      clock: function () {
        ch.send({ type: "broadcast", event: "clock", payload: { t: Date.now() } });
      },
      rename: function (name) {
        opts.name = name;
        ch.track({ role: opts.role, name: name, joined: joined });
      },
      offset: function () {
        return offset;
      }
    };
  }

  window.Party = {
    connect: connect,
    room: room,
    unlock: unlock,
    play: play,
    SOUNDS: SOUNDS,
    COLORS: COLORS
  };
})();
