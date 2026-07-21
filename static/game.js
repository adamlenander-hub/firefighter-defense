
    // Dials — MUST match the server (GameState). The spawn schedule itself is sent
    // by the server (level.schedule), so it isn't rebuilt here.
    var FIRE_PX_PER_SEC = 90.0;
    var TOWER_RANGE = 130.0, TOWER_COOLDOWN = 0.7, EXTINGUISH_REWARD = 12;
    var SMART_BONUS = 6, DANGER_SPEEDUP = 0.10;
    // ITEM-041: fires resist being put out — see the Python FIRE_HP/*_HIT_DAMAGE
    // comment for the full rule (good = one hit, weak = two).
    var FIRE_HP = 1.0, GOOD_HIT_DAMAGE = 1.0, WEAK_HIT_DAMAGE = 0.55;
    // ITEM-040: extinguishers deplete — see the Python TOWER_CHARGE_BASE/
    // CAMPAIGN_CHARGE_FACTOR comment for the full rule (charge tightens mission by
    // mission; only a shot that actually discharges AT the fire — good/weak/danger,
    // never a fully-useless one — spends it).
    var TOWER_CHARGE_BASE = 8;
    var CAMPAIGN_CHARGE_FACTOR = {1: 1.0, 2: 0.85, 3: 0.7, 4: 0.55};
    var MIN_TOWER_CHARGE = 3;
    function towerChargeFor(lv){
      var factor = (lv && lv.mission && CAMPAIGN_CHARGE_FACTOR[lv.mission]) || 1.0;
      return Math.max(MIN_TOWER_CHARGE, Math.round(TOWER_CHARGE_BASE * factor));
    }
    // ITEM-034: caps how many fires can ever be alive at once, so a chain of water
    // splitting a liquid/cooking-oil fire in two can never make a level unwinnable.
    var MAX_ACTIVE_FIRES = 14;

    // --- German→English in-game switch (i18n) ---------------------------------
    // The game is German-first; every player-visible German string that is hard-coded
    // in the browser (chrome, buttons, recap, library, tool-info, status/footer) lives
    // here as a de/en pair, read through tr(key). Content that comes from the server
    // (fire facts, Anton's lines, level names) is switched by re-fetching with ?lang=.
    // `lang` starts at 'de'; loadLang() below sets it from localStorage 'fd_lang'
    // (falling back to the served <html lang>). Named tr (not t) to avoid colliding
    // with the many local `t` variables in this file.
    var lang = 'de';
    var UI_STRINGS = {
      de: {
        subtitle: '🚒 Freiwillige Feuerwehr Königstein im Taunus · 150 Jahre',
        place_loading: 'Einsatz wird geladen …',
        menu_mission: '🎯 Mission ▾',
        btn_start: 'Einsatz starten',
        btn_running: 'Läuft …',
        btn_restart: 'Neu starten',
        lbl_contrast: 'Große Schrift / Hoher Kontrast',
        ui_sound: 'Ton',
        lib_btn: 'Antons Wissen',
        hint: 'Löscher wählen, dann auf einen blauen Bauplatz tippen. Der richtige Löscher löscht, der falsche wirkt nicht — ein gefährlicher lässt das Feuer auflodern. Löscher leeren sich (Anzeige am Turm) und müssen ersetzt werden. Falsch gebaut? Ohne gewählten Löscher auf den Turm tippen, um ihn abzubauen (keine Rückerstattung). Tastatur: 1–6 wählt den Löscher, Pfeiltasten wählen den Bauplatz, Enter setzt, Rücktaste/Entf baut ab, Leertaste startet.',
        legend_start: 'Start',
        legend_path: 'Weg zum Gebäude',
        legend_spot: 'Bauplatz für Löscher',
        legend_building: 'Gebäude',
        card_attrib: '— Anton, der Burggeist 👻',
        card_ok: 'Verstanden',
        lib_title: 'Antons Wissen 👻',
        lib_subtitle: 'Welcher Löscher passt zu welchem Feuer?',
        close: 'Schließen',
        vig_close: 'Weiter',
        fin_close: 'Zum Fest 🎉',
        pregame_title: 'So funktioniert\'s 🎮',
        pregame_ok: 'Los geht\'s! ▶',
        recap_won: 'Einsatz geschafft! 🎉',
        recap_lost: 'Einsatz gescheitert',
        recap_score: 'Wissenswertung: ',
        recap_of: ' von ',
        recap_ok: ' Feuern richtig gelöscht · ',
        recap_through: ' durchgekommen · ',
        recap_mistakes: ' Fehlversuche',
        recap_correct: 'Richtig: ',
        recap_these_fires: 'Diese Feuer kamen vor:',
        recap_loss_anton: 'Kein Grund zu hadern — beim nächsten Mal schaffen wir das zusammen.',
        recap_next: 'Nächster Einsatz ▶',
        lib_correct: '✓ Richtig: ',
        lib_dangerous: '⚠️ Gefährlich: ',
        lib_loading: 'Wird geladen …',
        tower_removed: 'Löscher abgebaut — keine Rückerstattung.',
        gas_off: 'Gaszufuhr abgesperrt — gut!',
        power_off: 'Strom abgeschaltet — gut!',
        info_waves: ' Wellen — Löscher bauen, dann starten.',
        info_won: 'Gewonnen!',
        info_lost: 'Verloren.',
        info_wave: 'Welle ',
        info_fires: ' Feuer',
        key_spot: '▶ Bauplatz ',
        building_fallback: 'Gebäude',
        anton_senses: '👻 Anton wittert hier Rauch',
        intro_mission: 'Einsatz ',
        anton_attrib_inline: '— Anton, der Burggeist',
        reset_confirm: 'Kampagne wirklich von vorne beginnen? Der Fortschritt wird gelöscht.',
        lvl_locked_title: 'Zuerst den vorherigen Einsatz gewinnen.',
        lvl_practice: 'Übung: ',
        lvl_reset: '↺ Neu beginnen',
        lvl_reset_title: 'Kampagnen-Fortschritt löschen und wieder bei Einsatz 1 beginnen',
        level_load_error: 'Einsatz konnte nicht geladen werden.',
        ti_cost: 'Kosten zum Aufstellen: 💰 ',
        ti_correct: '✓ Richtig gegen: ',
        ti_weak: '≈ Notfalls brauchbar: ',
        ti_danger: '⚠️ Gefährlich auf: ',
        status_db: 'Datenbank ',
        status_ready: 'bereit',
        status_missing: 'fehlt',
        status_classes: ' Brandklassen · ',
        status_tools: ' Löschmittel',
        info_label: 'ℹ Info',
        info_aria: 'Info: ',
        hazard_action_gas: 'Gaszufuhr absperren',
        hazard_action_power: 'Strom abschalten',
        hazard_button_gas: '🔧 Gas absperren',
        hazard_button_power: '⚡ Strom abschalten',
        hazard_warn_gas: 'Bei Gasbränden zuerst die Gaszufuhr absperren!',
        hazard_warn_power: 'Bei Elektrobränden zuerst den Strom abschalten!'
      },
      en: {
        subtitle: '🚒 Königstein Volunteer Fire Brigade in the Taunus · 150 years',
        place_loading: 'Mission is loading …',
        menu_mission: '🎯 Mission ▾',
        btn_start: 'Start mission',
        btn_running: 'Running …',
        btn_restart: 'Restart',
        lbl_contrast: 'Large text / high contrast',
        ui_sound: 'Sound',
        lib_btn: 'Anton\'s Knowledge',
        hint: 'Choose an extinguisher, then tap a blue build spot. The right extinguisher puts the fire out, the wrong one does nothing — a dangerous one makes the fire flare up. Extinguishers run out (see the gauge on the tower) and must be replaced. Built one wrongly? Tap the tower with no extinguisher selected to remove it (no refund). Keyboard: 1–6 selects the extinguisher, arrow keys pick the build spot, Enter places, Backspace/Delete removes, Space starts.',
        legend_start: 'Start',
        legend_path: 'Path to the building',
        legend_spot: 'Build spot for extinguishers',
        legend_building: 'Building',
        card_attrib: '— Anton, the castle ghost 👻',
        card_ok: 'Understood',
        lib_title: 'Anton\'s Knowledge 👻',
        lib_subtitle: 'Which extinguisher suits which fire?',
        close: 'Close',
        vig_close: 'Continue',
        fin_close: 'To the festival 🎉',
        pregame_title: 'How it works 🎮',
        pregame_ok: 'Let\'s go! ▶',
        recap_won: 'Mission complete! 🎉',
        recap_lost: 'Mission failed',
        recap_score: 'Knowledge score: ',
        recap_of: ' of ',
        recap_ok: ' fires put out correctly · ',
        recap_through: ' got through · ',
        recap_mistakes: ' wrong attempts',
        recap_correct: 'Correct: ',
        recap_these_fires: 'These fires appeared:',
        recap_loss_anton: 'No need to fret — next time we\'ll manage it together.',
        recap_next: 'Next mission ▶',
        lib_correct: '✓ Correct: ',
        lib_dangerous: '⚠️ Dangerous: ',
        lib_loading: 'Loading …',
        tower_removed: 'Extinguisher removed — no refund.',
        gas_off: 'Gas supply shut off — good!',
        power_off: 'Power switched off — good!',
        info_waves: ' waves — build extinguishers, then start.',
        info_won: 'Won!',
        info_lost: 'Lost.',
        info_wave: 'Wave ',
        info_fires: ' fires',
        key_spot: '▶ Build spot ',
        building_fallback: 'Building',
        anton_senses: '👻 Anton senses smoke here',
        intro_mission: 'Mission ',
        anton_attrib_inline: '— Anton, the castle ghost',
        reset_confirm: 'Really start the campaign over? Your progress will be erased.',
        lvl_locked_title: 'Win the previous mission first.',
        lvl_practice: 'Practice: ',
        lvl_reset: '↺ Start over',
        lvl_reset_title: 'Erase campaign progress and start again at mission 1',
        level_load_error: 'Mission could not be loaded.',
        ti_cost: 'Cost to place: 💰 ',
        ti_correct: '✓ Correct against: ',
        ti_weak: '≈ Usable in a pinch: ',
        ti_danger: '⚠️ Dangerous on: ',
        status_db: 'Database ',
        status_ready: 'ready',
        status_missing: 'missing',
        status_classes: ' fire classes · ',
        status_tools: ' extinguishers',
        info_label: 'ℹ Info',
        info_aria: 'Info: ',
        hazard_action_gas: 'Shut off the gas supply',
        hazard_action_power: 'Switch off the power',
        hazard_button_gas: '🔧 Shut off gas',
        hazard_button_power: '⚡ Switch off power',
        hazard_warn_gas: 'For gas fires, shut off the gas supply first!',
        hazard_warn_power: 'For electrical fires, switch off the power first!'
      }
    };
    function tr(key){
      var pack = UI_STRINGS[lang==='en'?'en':'de'] || UI_STRINGS.de;
      if (pack && pack[key]!=null) return pack[key];
      return (UI_STRINGS.de[key]!=null) ? UI_STRINGS.de[key] : key;
    }
    function apiLang(){ return '?lang=' + (lang==='en'?'en':'de'); }
    // Set every static [data-i18n] label from the current language.
    function applyStaticI18n(){
      var nodes = document.querySelectorAll('[data-i18n]');
      Array.prototype.forEach.call(nodes, function(el){
        var key = el.getAttribute('data-i18n');
        if (key) el.textContent = tr(key);
      });
    }

    // Supply-hazard mechanic (ITEM-016), mirroring the server. Kept in step with the
    // Python HAZARD_* constants. The labels are language-aware (read through tr).
    var HAZARD_CLASS = {gas: 'C', power: 'electrical'};
    function hazardAction(h){ return tr('hazard_action_' + h); }
    function hazardButton(h){ return tr('hazard_button_' + h); }
    function hazardWarn(h){ return tr('hazard_warn_' + h); }
    function gatedHazardFor(cls){
      if (!level || !level.supplies) return null;
      for (var i=0;i<level.supplies.length;i++){ if (HAZARD_CLASS[level.supplies[i]]===cls) return level.supplies[i]; }
      return null;
    }
    // Which hazard (if any) feeds this class, among a running game's supplies.
    function HAZARD_CLASS_OF_IN(g, cls){
      for (var h in g.supplies){ if (Object.prototype.hasOwnProperty.call(g.supplies,h) && HAZARD_CLASS[h]===cls) return h; }
      return null;
    }
    function rightActionFor(cid){
      var h=gatedHazardFor(cid);
      if (h) return hazardAction(h);
      var c=classMap[cid]||{}; return c.right_tool_de||'';
    }

    var canvas = document.getElementById('board');
    var ctx = canvas.getContext('2d');
    var level = null;       // the loaded level's map + waves + schedule
    var classMap = {};      // class id -> {icon, colour, letter, name_de}
    var toolMap = {};       // tool id -> {name_de, cost, short, hex}
    var toolsList = [];
    var matrixMap = {};     // "class|tool" -> outcome (good/weak/useless/danger)
    var reasonMap = {};     // "class|tool" -> Anton's feedback line (ITEM-012)
    var seen = {};          // fire classes already introduced this session (ITEM-011)
    var paused = false;     // true while an explanation card is up
    var feedbackUntil = 0;
    var selectedTool = null;
    var sprays = [];        // brief tower->fire lines to draw: {x1,y1,x2,y2,until}
    var game = null;        // running game state, or null before start
    var last = 0;
    // --- Anton-as-narrator + campaign state (ITEM-026 / ITEM-027) ---
    var antonLines = {};    // the loaded level's per-mission framing (open/anecdote/hint/close/bonus)
    var missionKey = null;  // stable level key, e.g. 'fachwerk'
    var missionNo = null;   // story mission number (1..4), or null for the side/training level
    var isCampaign = false; // true for the four story missions
    var hintShown = false;  // Anton's single in-play whisper per game (calm pacing)
    var levelsMeta = [];    // /api/levels list, with campaign metadata
    var currentIndex = -1;  // index of the level currently loaded
    var campaignProgress = 0; // highest story mission completed (persisted in the browser)
    // Anton's growth arc + reward scenes (ITEM-028)
    var antonArc = [];        // courage lines by missions-completed
    var antonFinale = {};     // the finale payload (title/caption/lines/scene)
    var vigRAF = null;        // the reward-scene animation handle (so it can be cancelled)
    var vignetteThenFinale = false; // after this vignette, play the finale?
    // Tablet / accessibility (ITEM-020) — all additive, desktop mouse unchanged.
    var HIT_RADIUS = 42;      // build-spot tap/click hit radius in board coords (finger-friendly)
    var keyIndex = -1;        // keyboard-highlighted build spot (-1 = none chosen yet)
    var keyboardActive = false; // draw the keyboard focus ring once the keyboard is used
    var contrastEnabled = false; // large-text / high-contrast mode

    // --- Friendly sound effects (ITEM-019) -----------------------------------
    // Sounds are GENERATED in the browser with the Web Audio API — there are NO
    // audio files, so nothing can fail to load (option A from the analysis). The
    // firm project rule "an optional part must never crash the page" is honoured
    // the same way the storage code is: the API is checked ONCE, and every audio
    // call is wrapped in try/catch. If audio is unsupported or anything throws,
    // the game simply carries on in silence with nothing shown to the player.
    var soundEnabled = true;                 // player-facing mute toggle (default: sound ON)
    var _AudioCtor = (typeof window !== 'undefined') && (window.AudioContext || window.webkitAudioContext);
    var audioSupported = !!_AudioCtor;       // decided once; if false we stay silent forever
    var audioCtx = null;                     // created lazily on the first user gesture
    var _lastSoundAt = 0;                    // light throttle so many towers can't stack a harsh pile-up

    // Autoplay-safe: browsers block sound until the player interacts. This is called
    // from the "Einsatz starten" button (a real user gesture) so the first effects
    // actually play. Guarded — a failure here just means the game stays quiet.
    function initAudio(){
      if (!audioSupported || !soundEnabled) return;
      try {
        if (!audioCtx) audioCtx = new _AudioCtor();
        if (audioCtx.state === 'suspended' && audioCtx.resume) audioCtx.resume();
      } catch (e){ /* audio unavailable — continue silently */ }
    }

    // One short, soft tone with a quick fade in/out (no clicks, nothing grating).
    function playTone(freq, startAt, dur, type, peak){
      if (!audioCtx) return;
      try {
        var t0 = audioCtx.currentTime + (startAt || 0);
        var osc = audioCtx.createOscillator();
        var gain = audioCtx.createGain();
        osc.type = type || 'sine';
        osc.frequency.setValueAtTime(freq, t0);
        var vol = (peak == null ? 0.11 : peak);
        gain.gain.setValueAtTime(0.0001, t0);
        gain.gain.exponentialRampToValueAtTime(vol, t0 + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
        osc.connect(gain); gain.connect(audioCtx.destination);
        osc.start(t0); osc.stop(t0 + dur + 0.03);
      } catch (e){ /* never let a sound break the page */ }
    }

    // The single guarded entry point every effect goes through. Respects mute and
    // the one-time support check, keeps sounds short, and lightly throttles the
    // reactive cues (good/danger/useless) so a frame with several towers firing
    // can't stack into a grating burst. Win/lose motifs are one-off and bypass it.
    function playSound(kind){
      if (!soundEnabled || !audioSupported) return;
      try {
        if (!audioCtx) return;                       // engine not unlocked yet — stay silent
        if (audioCtx.state === 'suspended' && audioCtx.resume) audioCtx.resume();
        if (kind === 'good' || kind === 'danger' || kind === 'useless'){
          var now = (audioCtx.currentTime || 0) * 1000;
          if (now - _lastSoundAt < 110) return;      // collapse same-frame repeats
          _lastSoundAt = now;
        }
        switch (kind){
          case 'good':                               // warm rising two-note — a correct extinguish
            playTone(523.25, 0,    0.12, 'sine', 0.10);
            playTone(783.99, 0.09, 0.16, 'sine', 0.10);
            break;
          case 'danger':                             // low soft buzz — a dangerous / wrong tool
            playTone(150, 0, 0.22, 'sawtooth', 0.07);
            break;
          case 'useless':                            // small subtle blip — a tool that does nothing
            playTone(320, 0, 0.06, 'triangle', 0.045);
            break;
          case 'win':                                // short cheerful up-motif at level won
            playTone(523.25, 0,    0.12, 'sine', 0.10);
            playTone(659.25, 0.11, 0.12, 'sine', 0.10);
            playTone(783.99, 0.22, 0.22, 'sine', 0.11);
            break;
          case 'lose':                               // gentle falling two-note at level lost
            playTone(392.00, 0,    0.16, 'sine', 0.09);
            playTone(261.63, 0.15, 0.28, 'sine', 0.09);
            break;
        }
      } catch (e){ /* an audio failure must never break or freeze the page */ }
    }

    // Mute persistence — same guarded localStorage pattern as loadContrast/saveContrast;
    // a browser that blocks storage must never throw. Default is sound ON.
    function saveSound(on){ try { window.localStorage.setItem('fd_sound', on ? '1':'0'); } catch(e){} }
    function loadSound(){
      var on = true;
      try { var v = window.localStorage.getItem('fd_sound'); if (v !== null) on = (v === '1'); }
      catch (e){ on = true; }
      soundEnabled = on;
      var cb = document.getElementById('soundToggle'); if (cb) cb.checked = on;
    }

    // Progress is stored in the browser so the fixed play order survives a reload.
    // Storage is optional — a browser that blocks it must never crash the page.
    function loadProgress(){
      try { var v = window.localStorage.getItem('fd_campaign_progress');
            campaignProgress = v ? (parseInt(v,10)||0) : 0; }
      catch (e) { campaignProgress = 0; }
    }
    function saveProgress(){
      try { window.localStorage.setItem('fd_campaign_progress', String(campaignProgress)); }
      catch (e) { /* storage unavailable — keep progress in memory only */ }
    }
    // Mission N is playable once the mission before it is won (mission 1 always is).
    function missionUnlocked(n){ return n <= campaignProgress + 1; }
    // Start the campaign over: clear saved progress and return to the locked state
    // with only mission 1 available. Storage clearing is guarded so it can't throw.
    function resetProgress(){
      if (typeof window.confirm === 'function' &&
          !window.confirm(tr('reset_confirm'))) return;
      campaignProgress = 0;
      try { window.localStorage.removeItem('fd_campaign_progress'); } catch (e) { /* storage off — ignore */ }
      renderLevelBar();
      var camp=levelsMeta.filter(function(l){ return l.campaign && l.mission; })
                         .slice().sort(function(a,b){ return a.mission-b.mission; });
      loadLevel(camp.length ? camp[0].index : 0);
    }

    function pathLength(wp) {
      var t = 0;
      for (var i = 1; i < wp.length; i++) t += Math.hypot(wp[i][0]-wp[i-1][0], wp[i][1]-wp[i-1][1]);
      return t;
    }
    // Same maths as the server's path_point_at: a point a fraction t along the path.
    function pathPointAt(wp, t) {
      if (!wp.length) return [0,0];
      if (t <= 0) return wp[0];
      if (t >= 1) return wp[wp.length-1];
      var total = pathLength(wp); if (!total) return wp[0];
      var target = t*total, walked = 0;
      for (var i = 1; i < wp.length; i++) {
        var seg = Math.hypot(wp[i][0]-wp[i-1][0], wp[i][1]-wp[i-1][1]);
        if (seg && walked + seg >= target) {
          var f = (target-walked)/seg;
          return [wp[i-1][0]+(wp[i][0]-wp[i-1][0])*f, wp[i-1][1]+(wp[i][1]-wp[i-1][1])*f];
        }
        walked += seg;
      }
      return wp[wp.length-1];
    }

    // --- drawing ---
    // --- ITEM-038 two-tone flat helpers (ported from the approved mockup) ------
    // Read a CSS variable (the flat palette), cached per theme so it's cheap per frame.
    var _cssv={}, _cssvKey='';
    function cssv(n){
      var key = contrastEnabled ? 'hc' : 'lt';
      if (key!==_cssvKey){ _cssv={}; _cssvKey=key; }
      if (_cssv[n]!==undefined) return _cssv[n];
      var v=''; try { v=getComputedStyle(document.body).getPropertyValue(n).trim(); } catch(e){ v=''; }
      _cssv[n]=v; return v;
    }
    // Mix a hex colour toward white (amt>0) or black (amt<0) — gives the 2nd flat tone.
    function shade(hex,amt){
      hex=(hex||'').replace('#',''); if(hex.length===3) hex=hex.split('').map(function(x){return x+x;}).join('');
      if(hex.length<6) return '#888';
      var r=parseInt(hex.substr(0,2),16), g=parseInt(hex.substr(2,2),16), b=parseInt(hex.substr(4,2),16);
      var t=amt<0?0:255, a=Math.abs(amt);
      r=Math.round(r+(t-r)*a); g=Math.round(g+(t-g)*a); b=Math.round(b+(t-b)*a);
      return 'rgb('+r+','+g+','+b+')';
    }
    // Rounded-rect path.
    function rr(c,x,y,w,h,r){ c.beginPath(); c.moveTo(x+r,y); c.arcTo(x+w,y,x+w,y+h,r); c.arcTo(x+w,y+h,x,y+h,r); c.arcTo(x,y+h,x,y,r); c.arcTo(x,y,x+w,y,r); c.closePath(); }
    // The ONE allowed background gradient (sky), computed ONCE per size/theme.
    var _skyGrad=null, _skyKey='';
    function skyGradient(w,h){
      var key=w+'x'+h+(contrastEnabled?'d':'l');
      if(key!==_skyKey){
        var g=ctx.createLinearGradient(0,0,0,h);
        if(contrastEnabled){ g.addColorStop(0,'#0b0d12'); g.addColorStop(1,'#161f2b'); }
        else { g.addColorStop(0,'#e6effb'); g.addColorStop(1,'#f6f9fd'); }
        _skyGrad=g; _skyKey=key;
      }
      return _skyGrad;
    }
    // A fire class -> its flat-palette colour (visual only; letter/icon unchanged).
    var _CLASS_VAR={A:'--a',B:'--b',C:'--c',electrical:'--e',D:'--d',F:'--f'};
    function classColour(cls){ return cssv(_CLASS_VAR[cls]||'') || (classMap[cls]&&classMap[cls].colour) || '#e4572e'; }
    function flameShape(c,s,sc){ c.beginPath(); c.moveTo(0,-s*sc);
      c.bezierCurveTo(s*0.9*sc,-s*0.5*sc, s*0.75*sc,s*0.7*sc, 0,s*sc);
      c.bezierCurveTo(-s*0.75*sc,s*0.7*sc, -s*0.9*sc,-s*0.5*sc, 0,-s*sc); c.closePath(); }
    // Two-tone flat extinguisher body in the tool colour. Takes a context so it can
    // be drawn on the board (towers) AND on the little palette canvases (ITEM-036).
    function drawExtShape(c,x,y,w,h,col){
      c.save();
      c.fillStyle=col; rr(c,x,y,w,h,w*0.36); c.fill();
      c.save(); rr(c,x,y,w,h,w*0.36); c.clip();
      c.fillStyle=shade(col,-0.22); c.fillRect(x+w*0.55,y,w*0.5,h);
      c.fillStyle=shade(col,0.35); c.fillRect(x,y,w*0.16,h);
      c.restore();
      c.fillStyle=cssv('--ink')||'#1f2937'; rr(c,x+w*0.32,y-h*0.14,w*0.36,h*0.14,3); c.fill();
      rr(c,x+w*0.12,y-h*0.05,w*0.76,h*0.09,3); c.fill();
      c.fillStyle='#ffffff'; rr(c,x+w*0.2,y+h*0.30,w*0.6,h*0.3,4); c.fill();
      c.restore();
    }
    // Tool colour, lightened in high-contrast so a dark tool still reads on a dark field.
    function toolColour(hex){ return contrastEnabled ? shade(hex||'#334155',0.4) : (hex||'#334155'); }

    function trace(wp) { ctx.beginPath(); ctx.moveTo(wp[0][0], wp[0][1]); for (var i=1;i<wp.length;i++) ctx.lineTo(wp[i][0],wp[i][1]); }
    // The shared two-tone rounded ribbon — the clear walking lane under every material.
    function drawRibbon(wp, road){
      ctx.lineCap='round'; ctx.lineJoin='round';
      ctx.strokeStyle=road; ctx.lineWidth=44; trace(wp); ctx.stroke();
      ctx.strokeStyle=shade(road,0.22); ctx.lineWidth=44; ctx.save(); ctx.translate(0,-7); trace(wp); ctx.stroke(); ctx.restore();
      ctx.strokeStyle=road; ctx.lineWidth=30; trace(wp); ctx.stroke();
    }
    // Unit tangent along the path at fraction t (for placing material motifs).
    function pathTangentAt(wp, t){
      var d=0.004, a=pathPointAt(wp, Math.max(0,t-d)), b=pathPointAt(wp, Math.min(1,t+d));
      var dx=b[0]-a[0], dy=b[1]-a[1], L=Math.hypot(dx,dy)||1; return [dx/L, dy/L];
    }
    // Evenly-spaced points along the path with a perpendicular (across-lane) vector.
    // Cached per level+spacing so it is computed ONCE, not per frame (performance).
    var _motifCache={};
    function pathMotifs(wp, spacing){
      var key=(level&&level.key||'')+'|'+spacing+'|'+wp.length;
      if (_motifCache[key]) return _motifCache[key];
      var total=pathLength(wp), n=Math.max(2, Math.floor(total/spacing)), arr=[];
      for (var i=0;i<=n;i++){ var t=i/n, p=pathPointAt(wp,t), tg=pathTangentAt(wp,t);
        arr.push({x:p[0], y:p[1], nx:-tg[1], ny:tg[0]}); }
      _motifCache[key]=arr; return arr;
    }
    // --- ITEM-044: per-mission path material (picked by the level's key) ---------
    // Each keeps the clear ribbon lane; the material is a themed overlay on top, and
    // every material function is high-contrast aware so the lane stays legible.
    function drawPathTimber(wp){                 // mission 1 — timber planks / boardwalk
      var hc=contrastEnabled; drawRibbon(wp, hc?'#4a3826':'#b98a5a');
      var plank=hc?'#6b5236':'#8a6238', edge=hc?'#241a10':shade(plank,-0.28);
      ctx.lineCap='butt';
      pathMotifs(wp,26).forEach(function(m){ var hw=16;
        ctx.strokeStyle=edge; ctx.lineWidth=7; ctx.beginPath(); ctx.moveTo(m.x-m.nx*hw,m.y-m.ny*hw); ctx.lineTo(m.x+m.nx*hw,m.y+m.ny*hw); ctx.stroke();
        ctx.strokeStyle=plank; ctx.lineWidth=4; ctx.beginPath(); ctx.moveTo(m.x-m.nx*hw,m.y-m.ny*hw); ctx.lineTo(m.x+m.nx*hw,m.y+m.ny*hw); ctx.stroke(); });
      ctx.lineCap='round';
    }
    function drawPathBooks(wp){                  // mission 2 — flat books lying scattered along the trail (ITEM-059)
      var hc=contrastEnabled; drawRibbon(wp, hc?'#2b3546':'#d9c9a8');
      var covers=hc?['#7cb0ff','#ffc247','#ff86d3','#4fe6cf','#c4b5fd']:['#2f6fed','#e4572e','#8b5cf6','#14b8a6','#d6a409'];
      // Stable pseudo-random per book index (NOT per frame) so the scatter holds still.
      function h(n){ var x=Math.sin(n*12.9898)*43758.5453; return x-Math.floor(x); }
      pathMotifs(wp,22).forEach(function(m,i){
        var col=covers[i%covers.length];
        var off=(h(i*2+1)-0.5)*20, along=(h(i*2+7)-0.5)*14;   // scatter across + a little along the lane
        var ang=(h(i*3+2)-0.5)*Math.PI;                        // any angle — haphazard, not aligned to the lane
        var bw=17+h(i+5)*7, bh=12+h(i+9)*5;                    // varied book size
        ctx.save();
        ctx.translate(m.x+m.nx*off+m.ny*along, m.y+m.ny*off-m.nx*along);
        ctx.rotate(ang);
        ctx.fillStyle=shade(col,-0.32); rr(ctx,-bw/2-1.5,-bh/2+2,bw,bh,2.5); ctx.fill();   // underside/shadow — books lie flat, face-up
        ctx.fillStyle=col; rr(ctx,-bw/2,-bh/2,bw,bh,2.5); ctx.fill();                        // cover
        ctx.fillStyle=shade(col,-0.4); ctx.fillRect(-bw/2,-bh/2,3.5,bh);                     // spine down the left edge
        ctx.fillStyle=hc?'#e5e7eb':'#fdfaf0'; ctx.fillRect(bw/2-3,-bh/2+2,2.5,bh-4);         // page block on the right edge
        ctx.strokeStyle=hc?'rgba(255,255,255,.55)':'rgba(255,255,255,.8)'; ctx.lineWidth=1.4; ctx.lineCap='round';
        ctx.beginPath(); ctx.moveTo(-bw/2+6,-bh*0.12); ctx.lineTo(bw/2-6,-bh*0.12); ctx.moveTo(-bw/2+6,bh*0.16); ctx.lineTo(bw/2-8,bh*0.16); ctx.stroke();  // title lines
        ctx.restore();
      });
    }
    function drawPathGravel(wp){                 // mission 3 — park gravel / earth trail
      var hc=contrastEnabled; drawRibbon(wp, hc?'#333e30':'#c9b48f');
      var g1=hc?'#5a674f':'#a8926b', g2=hc?'#414c3c':'#8f7a58';
      pathMotifs(wp,13).forEach(function(m,i){ var off=((i*37)%9-4);
        ctx.fillStyle=(i%2)?g1:g2; ctx.beginPath(); ctx.arc(m.x+m.nx*off, m.y+m.ny*off, (i%3)+1.6, 0, Math.PI*2); ctx.fill(); });
    }
    function drawPathChips(wp){                  // mission 4 — festival wood chips
      var hc=contrastEnabled; drawRibbon(wp, hc?'#3a2c1c':'#caa778');
      var c1=hc?'#7a5a38':'#a97e4e', c2=hc?'#5b4326':'#8a6238';
      pathMotifs(wp,15).forEach(function(m,i){ var off=((i*29)%11-5);
        ctx.save(); ctx.translate(m.x+m.nx*off, m.y+m.ny*off); ctx.rotate(i*1.3);
        ctx.fillStyle=(i%2)?c1:c2; rr(ctx,-4,-1.7,8,3.4,1.4); ctx.fill(); ctx.restore(); });
    }
    function drawPathCables(wp){                 // Schlosserei — cables + a gas line
      var hc=contrastEnabled; drawRibbon(wp, hc?'#20262f':'#b8c2cf');
      function line(off,col,wd){ ctx.strokeStyle=col; ctx.lineWidth=wd; ctx.lineCap='round';
        ctx.beginPath(); pathMotifs(wp,8).forEach(function(m,i){ var px=m.x+m.nx*off, py=m.y+m.ny*off; i?ctx.lineTo(px,py):ctx.moveTo(px,py); }); ctx.stroke(); }
      line(-8, hc?'#ff7a4d':'#e4572e', 3.5);     // red cable
      line(0,  hc?'#ffc247':'#d6a409', 3.5);     // yellow gas line
      line(8,  hc?'#7cb0ff':'#2f6fed', 3.5);     // blue cable
    }
    function drawPath(wp){
      var key=level&&level.key;
      if (key==='fachwerk')       drawPathTimber(wp);
      else if (key==='bibliothek')drawPathBooks(wp);
      else if (key==='kurpark')   drawPathGravel(wp);
      else if (key==='feuerwerk') drawPathChips(wp);
      else if (key==='schlosserei')drawPathCables(wp);
      else {                                     // generic fallback ribbon + centre line
        var road=contrastEnabled?'#2b3546':'#c3cfdd'; drawRibbon(wp, road);
        ctx.strokeStyle=shade(road, contrastEnabled?0.4:-0.08); ctx.lineWidth=3; ctx.setLineDash([12,14]); trace(wp); ctx.stroke(); ctx.setLineDash([]);
      }
    }
    function drawBuildSpot(x,y){
      // ITEM-056 (replaces ITEM-049): an open build spot is a solid black circle with
      // a white border, drawn the SAME in every mode (normal + high-contrast) so it
      // stands out against any mission background. Radius kept at 24. A thin outer
      // dark edge keeps the white border readable even on a near-white background.
      ctx.beginPath(); ctx.arc(x,y,24,0,Math.PI*2);
      ctx.fillStyle='#000000'; ctx.fill();
      ctx.lineWidth=3; ctx.strokeStyle='#ffffff'; ctx.stroke();
      ctx.lineWidth=1; ctx.strokeStyle='rgba(0,0,0,0.55)'; ctx.beginPath(); ctx.arc(x,y,25.5,0,Math.PI*2); ctx.stroke();
    }
    // A clear focus ring on the keyboard-highlighted build spot (ITEM-020), so a
    // keyboard player can always see where they are.
    function drawKeyHighlight(){
      if (!keyboardActive || !level || keyIndex<0 || keyIndex>=level.build_spots.length) return;
      var s=level.build_spots[keyIndex];
      var pulse=30 + Math.sin(performance.now()/220)*3;
      ctx.save();
      ctx.strokeStyle='#f59e0b'; ctx.lineWidth=4;
      ctx.beginPath(); ctx.arc(s[0],s[1],pulse,0,Math.PI*2); ctx.stroke();
      ctx.strokeStyle='#78350f'; ctx.lineWidth=1.5;
      ctx.beginPath(); ctx.arc(s[0],s[1],pulse+3,0,Math.PI*2); ctx.stroke();
      ctx.fillStyle='#b45309'; ctx.font='bold 12px system-ui'; ctx.textAlign='center';
      ctx.fillText(tr('key_spot') + (keyIndex+1), s[0], s[1]-pulse-6);
      ctx.restore();
    }
    function drawStart(wp){
      var b=cssv('--blue')||'#2f6fed';
      ctx.fillStyle=shade(b,-0.15); ctx.beginPath(); ctx.arc(wp[0][0],wp[0][1],13,0,Math.PI*2); ctx.fill();
      ctx.fillStyle=b; ctx.beginPath(); ctx.arc(wp[0][0],wp[0][1],8,0,Math.PI*2); ctx.fill();
      ctx.fillStyle=cssv('--muted')||'#5b6b7f'; ctx.font='600 12px system-ui'; ctx.textAlign='center'; ctx.fillText(tr('legend_start'), wp[0][0], wp[0][1]-20);
    }
    // Two-tone flat house; KEEPS the red damage flash + the HTML lives display.
    // ITEM-033: how battered the building looks, driven by remaining lives (0 =
    // pristine .. 3 = smoking ruin). Presentation only — the lose condition itself
    // is still lives<=0 in advance(), completely unchanged.
    function buildingDamageStage(){
      if (!game || !game.level || !game.level.building) return 0;
      var start = game.level.building.lives || 1;
      var remainFrac = Math.max(0, game.lives) / start;
      if (remainFrac <= 0) return 3;
      if (remainFrac <= 0.4) return 2;
      if (remainFrac < 1) return 1;
      return 0;
    }
    // ITEM-058 house-fire helpers. Everything is greyscale/high-contrast safe: the
    // three damage stages are told apart by AMOUNT — size + number of flames, height
    // of the smoke column, and (at the ruin) a structural roof collapse — never by
    // hue alone. Flames flicker and smoke rises cheaply off performance.now(), and hc
    // forces bright flame fills, white smoke and black/white structure.
    function houseFlame(fx, baseY, s, ph, hc){            // one animated flame, base anchored, rising up
      var flick = 0.5+0.5*Math.sin(performance.now()*0.006 + ph);
      ctx.save();
      ctx.translate(fx, baseY - s);
      var lean = (flick-0.5)*0.5;
      ctx.transform(1,0,lean,1,-lean*s,0);               // sway anchored at the base (y=+s)
      ctx.globalAlpha = 0.9;
      ctx.fillStyle = hc?'#ffb703':'#f97316';            // outer flame
      flameShape(ctx, s, 1 + flick*0.08); ctx.fill();
      ctx.save(); ctx.translate(0, s*0.22);
      ctx.fillStyle = hc?'#fff3b0':'#fbbf24';            // hot inner core
      flameShape(ctx, s*0.9, 0.5 + flick*0.22); ctx.fill(); ctx.restore();
      ctx.globalAlpha = 1;
      ctx.restore();
    }
    function housePlume(cx, topY, hc, count, spread, height){   // rising smoke column
      var now=performance.now()*0.001;
      ctx.save(); ctx.fillStyle = hc?'rgba(255,255,255,.6)':'rgba(64,64,64,.5)';
      for (var i=0;i<count;i++){
        var p=((now*0.3 + i/count)%1);
        var sx=cx + Math.sin(now*0.8 + i*1.3)*spread*(0.4+p);
        var sy=topY - p*height;
        ctx.globalAlpha = Math.max(0, 0.6*(1-p*0.9));
        ctx.beginPath(); ctx.arc(sx, sy, 5 + height*0.22*p, 0, Math.PI*2); ctx.fill();
      }
      ctx.globalAlpha = 1; ctx.restore();
    }
    function houseEmbers(cx, baseY, hc, spread, n){       // glowing embers drifting up
      var now=performance.now()*0.001;
      ctx.save();
      for (var i=0;i<n;i++){
        var p=((now*1.0 + i*0.41)%1);
        var ex=cx + Math.sin(now*3 + i*2.1)*spread;
        var ey=baseY - p*44;
        ctx.globalAlpha = Math.max(0,1-p);
        ctx.fillStyle = hc?'#ffffff':'#fde047';
        ctx.beginPath(); ctx.arc(ex, ey, 1.4 + 1.6*(1-p), 0, Math.PI*2); ctx.fill();
      }
      ctx.globalAlpha = 1; ctx.restore();
    }
    function houseScorch(x,bodyY,W,bodyH,hc,intensity){   // soot scorching up the walls
      ctx.save(); ctx.globalAlpha=(hc?0.5:0.32)*intensity; ctx.fillStyle = hc?'#000':'#1c1c1c';
      for (var i=0;i<4;i++){
        var sx=x+W*(0.14+i*0.24);
        ctx.beginPath(); ctx.moveTo(sx-7,bodyY+bodyH*0.2); ctx.quadraticCurveTo(sx-2,bodyY-10,sx+8,bodyY-24);
        ctx.lineTo(sx+2,bodyY-24); ctx.quadraticCurveTo(sx-7,bodyY-2,sx,bodyY+bodyH*0.2); ctx.closePath(); ctx.fill();
      }
      ctx.restore();
    }
    // The staged fire/ruin overlay, drawn on top of the (degraded) house.
    function drawHouseDamage(stage,x,bodyY,W,bodyH,yTop,bx,hc){
      houseScorch(x,bodyY,W,bodyH,hc, stage>=2?1:0.7);
      if (stage===1){                                     // a real, serious fire: several big flames + a tall window flame + a big plume
        houseFlame(x+W*0.24, bodyY+2,  bodyH*0.46, 0.6, hc);   // left roof
        houseFlame(x+W*0.52, yTop+4,   bodyH*0.52, 1.9, hc);   // near the apex
        houseFlame(x+W*0.76, bodyY+2,  bodyH*0.48, 0.0, hc);   // right roof
        houseFlame(x+21,     bodyY+30, bodyH*0.40, 1.1, hc);   // window, tall
        housePlume(bx+6, yTop-6, hc, 7, 15, 78);
        houseEmbers(bx, bodyY, hc, W*0.4, 5);
      } else if (stage===2){                              // fully engulfed: many huge flames swallowing the house, thick smoke, embers
        houseFlame(x+W*0.14, bodyY+4,  bodyH*0.56, 0.3, hc);
        houseFlame(x+W*0.34, yTop-2,   bodyH*0.64, 1.7, hc);   // over the roof
        houseFlame(x+W*0.52, yTop+2,   bodyH*0.70, 3.1, hc);   // apex, tallest
        houseFlame(x+W*0.70, yTop-2,   bodyH*0.64, 4.5, hc);
        houseFlame(x+W*0.88, bodyY+4,  bodyH*0.56, 5.6, hc);
        houseFlame(x+21,     bodyY+30, bodyH*0.50, 3.4, hc);   // blown-out window
        houseFlame(bx,       bodyY+bodyH*0.5, bodyH*0.46, 4.2, hc);   // door
        housePlume(bx, yTop-8, hc, 10, 22, 104);
        houseEmbers(bx, bodyY, hc, W*0.6, 14);
      } else if (stage>=3){                               // smoking ruin: burned out, no active fire — a big billowing smoke column dominates
        housePlume(bx-6, bodyY-6, hc, 14, 26, 150);
        houseEmbers(bx, bodyY+bodyH*0.55, hc, W*0.4, 4);      // a few faint dim smoulders
      }
    }
    function drawBuilding(b){
      var flashing = game && performance.now() < game.flashUntil;
      var hc=contrastEnabled;
      var stage = buildingDamageStage();
      var cream = flashing ? (hc?'#7a2b1e':'#f2b0a0') : (hc?'#e9d9b8':'#f3e4c2');
      if (stage>=3) cream = hc?'#2b2f36':'#3a352e';        // charred, near-black walls
      else if (stage===2) cream = shade(cream,-0.18);      // heavily scorched
      else if (stage===1) cream = shade(cream,-0.08);      // singed
      var W=94, H=76, x=b.x-W/2, yTop=b.y-H/2;
      var bodyY=yTop+18, bodyH=H-18;
      // body — TONE1 + a TONE2 shadow plane on the right third
      ctx.fillStyle=cream; rr(ctx,x,bodyY,W,bodyH,12); ctx.fill();
      ctx.save(); rr(ctx,x,bodyY,W,bodyH,12); ctx.clip(); ctx.fillStyle=shade(cream,-0.12); ctx.fillRect(x+W*0.66,bodyY,W*0.34,bodyH); ctx.restore();
      // ruin: a jagged structural crack splitting the charred body
      if (stage>=3){
        ctx.save(); ctx.strokeStyle=hc?'#000':'#141414'; ctx.lineWidth=2.5; ctx.lineJoin='round';
        ctx.beginPath(); ctx.moveTo(x+W*0.42,bodyY); ctx.lineTo(x+W*0.52,bodyY+bodyH*0.38); ctx.lineTo(x+W*0.44,bodyY+bodyH*0.68); ctx.lineTo(x+W*0.52,bodyY+bodyH); ctx.stroke();
        ctx.restore();
      }
      // roof — intact red triangle (bright on damage flash) until the ruin, when it COLLAPSES into a broken slump
      var red = flashing ? (hc?'#ff5a4d':'#dc2626') : (cssv('--red')||'#e4572e');
      if (stage>=3){
        red = hc?'#26282d':'#2a2621';                      // burnt-out, no more red
        ctx.fillStyle=red; ctx.beginPath();
        ctx.moveTo(x-6,bodyY+4);
        ctx.lineTo(x+W*0.20,bodyY-6); ctx.lineTo(x+W*0.34,bodyY+9);
        ctx.lineTo(x+W*0.52,bodyY-8); ctx.lineTo(x+W*0.68,bodyY+11);
        ctx.lineTo(x+W*0.86,bodyY-2); ctx.lineTo(x+W+6,bodyY+4);
        ctx.closePath(); ctx.fill();
      } else {
        if (stage>=1) red = shade(red,-0.16*stage);        // roof scorches as it burns
        ctx.fillStyle=red; ctx.beginPath(); ctx.moveTo(x-6,bodyY+4); ctx.lineTo(x+W/2,yTop-8); ctx.lineTo(x+W+6,bodyY+4); ctx.closePath(); ctx.fill();
        ctx.fillStyle=shade(red,-0.2); ctx.fillRect(x-6,bodyY,W+12,6);
      }
      // door + window — two-tone blue (dark/unlit as a ruin; window blown out once badly ablaze)
      var blue=cssv('--blue')||'#2f6fed', lit = stage<3;
      ctx.fillStyle=shade(blue,-0.15); rr(ctx,x+W/2-14,bodyY+18,28,bodyH-18,6); ctx.fill();
      ctx.fillStyle= lit ? blue : shade(blue,-0.5); rr(ctx,x+W/2-10,bodyY+22,20,bodyH-22,4); ctx.fill();
      if (stage>=2){                                       // blown-out window: dark hole + jagged glass shards
        ctx.fillStyle= hc?'#000':'#160f06'; rr(ctx,x+12,bodyY+12,18,18,4); ctx.fill();
        ctx.strokeStyle= hc?'#fff':'#4a3720'; ctx.lineWidth=1.4;
        ctx.beginPath();
        ctx.moveTo(x+12,bodyY+12); ctx.lineTo(x+20,bodyY+21); ctx.lineTo(x+14,bodyY+30);
        ctx.moveTo(x+30,bodyY+13); ctx.lineTo(x+22,bodyY+22); ctx.lineTo(x+28,bodyY+30);
        ctx.stroke();
      } else {
        ctx.fillStyle= shade(blue,0.55); rr(ctx,x+12,bodyY+12,18,18,4); ctx.fill();
      }
      // name label
      ctx.fillStyle=cssv('--ink')||'#1f2937'; ctx.font='700 13px system-ui'; ctx.textAlign='center';
      ctx.fillText(b.name_de||tr('building_fallback'), b.x, bodyY+bodyH+16);
      // ITEM-058: the dramatic staged fire/ruin overlay itself
      if (stage>=1) drawHouseDamage(stage,x,bodyY,W,bodyH,yTop,b.x,hc);
    }
    // --- ITEM-039: distinctive animated fire characters, one per class ----------
    // Each fire is a bigger evil-faced character whose SHAPE + idle animation reflect
    // its type, drawn on top of the ITEM-038 two-tone flame + palette. The class
    // LETTER badge + emoji icon + reaction-ring shapes are KEPT exactly (greyscale-
    // and high-contrast-safe, ITEM-008) — the character art is decoration, never a
    // replacement. Animation is cheap sin/time off the render clock, with a per-fire
    // phase so a crowd doesn't pulse in lockstep. No fire fact / balance touched.
    function drawEvilFace(c, s, sparkEyes, tt, ph){
      c.fillStyle='#fff';
      c.beginPath(); c.arc(-s*0.28,-s*0.05,s*0.17,0,Math.PI*2); c.arc(s*0.28,-s*0.05,s*0.17,0,Math.PI*2); c.fill();
      if (sparkEyes){                       // jagged yellow spark pupils (electrical / metal)
        c.fillStyle='#fde047';
        for (var k=0;k<2;k++){ var ex=(k?1:-1)*s*0.28;
          c.beginPath();
          for (var a=0;a<8;a++){ var ang=a*Math.PI/4 + tt*3 + ph; var rad=(a%2? s*0.15 : s*0.06);
            var px=ex+Math.cos(ang)*rad, py=-s*0.05+Math.sin(ang)*rad; a?c.lineTo(px,py):c.moveTo(px,py); }
          c.closePath(); c.fill(); }
      } else {
        c.fillStyle='#101418';
        c.beginPath(); c.arc(-s*0.28,-s*0.02,s*0.07,0,Math.PI*2); c.arc(s*0.28,-s*0.02,s*0.07,0,Math.PI*2); c.fill();
      }
      c.strokeStyle='#101418'; c.lineWidth=Math.max(2,s*0.06); c.lineCap='round';
      c.beginPath(); c.moveTo(-s*0.45,-s*0.35); c.lineTo(-s*0.12,-s*0.2); c.moveTo(s*0.45,-s*0.35); c.lineTo(s*0.12,-s*0.2); c.stroke();
      c.beginPath(); c.moveTo(-s*0.2,s*0.34); c.quadraticCurveTo(0,s*0.5,s*0.2,s*0.34); c.stroke();
    }
    // The shared two-tone flame body. ITEM-052: the motion is turned up so fires read as
    // lively rather than nearly still — the flame licks side to side (anchored at its base
    // so it doesn't drift off the burning object), the whole flame breathes, and the hot
    // inner core flickers harder. All driven off the existing per-fire flicker value, so no
    // extra work per frame and each fire still moves on its own phase. Works at any size, so
    // it composes with the bigger flames (ITEM-051) and the resist-shrink (ITEM-041).
    function drawFlameBody(c, s, col, flick){
      var lean = flick*0.16;                       // side-to-side lick amount
      c.save();
      c.transform(1, 0, lean, 1, -lean*s, 0);      // shear anchored at the base (y=+s): the tip sways, the base stays put
      c.fillStyle=col; flameShape(c, s, 1 + flick*0.06); c.fill();                         // outer flame breathes
      c.save(); c.translate(0, s*0.18); c.fillStyle=shade(col,0.42); flameShape(c, s, 0.55 + flick*0.22); c.fill(); c.restore();  // inner core flickers harder
      c.restore();
    }
    // Draw the per-type character in the fire's local (translated) coordinates.
    function drawFireCharacter(c, cls, s, col, tt, ph, hc){
      var flick = Math.sin(tt*8 + ph);
      if (cls==='F'){                        // cooking oil — a burning pan
        drawFlameBody(c, s*0.9, col, flick);
        drawEvilFace(c, s*0.9, false, tt, ph);
        c.fillStyle = hc ? '#c3cee0' : '#2b3546';   // dark pan silhouette at the base
        c.beginPath(); c.ellipse(0, s*0.72, s*0.7, s*0.22, 0, 0, Math.PI); c.fill();
        rr(c, -s*0.72, s*0.6, s*1.44, s*0.16, s*0.06); c.fill();
        rr(c, s*0.66, s*0.58, s*0.72, s*0.12, s*0.05); c.fill();   // handle
      } else if (cls==='B'){                 // liquids — bubbling green pool with flames
        var green = hc ? '#5fd47a' : '#2ba84a';
        c.save();                            // green pool (two-tone ellipse)
        c.fillStyle=shade(green,-0.2); c.beginPath(); c.ellipse(0, s*0.72, s*0.85, s*0.3, 0,0,Math.PI*2); c.fill();
        c.fillStyle=green; c.beginPath(); c.ellipse(0, s*0.68, s*0.78, s*0.24, 0,0,Math.PI*2); c.fill();
        c.restore();
        drawFlameBody(c, s*0.92, col, flick);       // flames (class colour) on the liquid
        for (var bi=0; bi<3; bi++){                  // rising bubbles
          var bp=((tt*0.6 + bi*0.4 + ph)%1), by=s*0.72 - bp*s, bx=(bi-1)*s*0.32;
          c.globalAlpha=Math.max(0,1-bp); c.fillStyle=shade(green,0.5);
          c.beginPath(); c.arc(bx, by, s*0.1*(1-bp*0.4), 0, Math.PI*2); c.fill();
        }
        c.globalAlpha=1;
        drawEvilFace(c, s*0.92, false, tt, ph);
      } else if (cls==='electrical'){        // electrical — spark eyes + thrown mini-sparks
        drawFlameBody(c, s, col, flick);
        c.strokeStyle = hc ? '#fff27a' : '#fde047'; c.lineWidth=Math.max(1.5,s*0.05); c.lineCap='round';
        for (var si=0; si<4; si++){
          var sp=((tt*1.4 + si*0.25 + ph)%1), ang=ph + si*1.9 + tt*0.5, r0=s*0.6 + sp*s*0.9;
          var sx=Math.cos(ang)*r0, sy=Math.sin(ang)*r0 - s*0.1;
          c.globalAlpha=Math.max(0,1-sp);
          c.beginPath(); c.moveTo(sx,sy); c.lineTo(sx+Math.cos(ang)*s*0.22, sy+Math.sin(ang)*s*0.22); c.stroke();
        }
        c.globalAlpha=1;
        c.beginPath(); c.moveTo(-s*0.1,-s*0.5); c.lineTo(s*0.06,-s*0.2); c.lineTo(-s*0.05,-s*0.05); c.lineTo(s*0.1,s*0.25); c.stroke();
        drawEvilFace(c, s, true, tt, ph);
      } else if (cls==='D'){                 // metals — intense white-hot spark-burst
        var white = hc ? '#ffffff' : '#f8fafc';
        drawFlameBody(c, s, col, flick);
        c.fillStyle='rgba(255,255,255,'+(0.5+0.35*Math.abs(Math.sin(tt*7+ph)))+')';
        c.beginPath(); c.arc(0, s*0.05, s*0.32, 0, Math.PI*2); c.fill();
        var burst=0.5+0.5*Math.sin(tt*9+ph);
        c.strokeStyle=white; c.lineWidth=Math.max(1.5,s*0.055); c.lineCap='round';
        for (var di=0; di<8; di++){ var a2=di*Math.PI/4 + tt*0.8, r1=s*0.5, r2=s*(0.8+0.35*burst);
          c.globalAlpha=0.4+0.5*burst;
          c.beginPath(); c.moveTo(Math.cos(a2)*r1, Math.sin(a2)*r1 - s*0.05); c.lineTo(Math.cos(a2)*r2, Math.sin(a2)*r2 - s*0.05); c.stroke(); }
        c.globalAlpha=1;
        drawEvilFace(c, s, true, tt, ph);
      } else if (cls==='C'){                 // gases — a sharp hissing jet flame + valve
        var jw=Math.sin(tt*10+ph)*s*0.12;
        c.fillStyle=shade(col,-0.3); rr(c, -s*0.2, s*0.55, s*0.4, s*0.35, s*0.08); c.fill();   // valve
        c.save(); c.translate(0,-s*0.1);
        c.fillStyle=col;                     // sharp elongated jet with a waver
        c.beginPath(); c.moveTo(-s*0.35,s*0.5); c.quadraticCurveTo(-s*0.1+jw,-s*0.4, jw,-s*1.05); c.quadraticCurveTo(s*0.1+jw,-s*0.4, s*0.35,s*0.5); c.closePath(); c.fill();
        c.fillStyle=shade(col,0.4);
        c.beginPath(); c.moveTo(-s*0.16,s*0.4); c.quadraticCurveTo(jw,-s*0.2, jw*0.6,-s*0.7); c.quadraticCurveTo(s*0.16,-s*0.2, s*0.16,s*0.4); c.closePath(); c.fill();
        c.restore();
        drawEvilFace(c, s, false, tt, ph);
      } else {                               // solids (A) + fallback — classic flame + ember log
        drawFlameBody(c, s, col, flick);
        c.fillStyle = hc ? '#5b3a22' : '#7a4a25';   // glowing ember log at the base
        rr(c, -s*0.5, s*0.62, s*1.0, s*0.28, s*0.12); c.fill();
        var eg=0.5+0.5*Math.sin(tt*6+ph);
        c.fillStyle='rgba(255,170,60,'+(0.35+0.4*eg)+')';
        c.beginPath(); c.arc(-s*0.2, s*0.76, s*0.08, 0, Math.PI*2); c.arc(s*0.18, s*0.76, s*0.07, 0, Math.PI*2); c.fill();
        drawEvilFace(c, s, false, tt, ph);
      }
    }
    function drawFire(f){
      var p = pathPointAt(game.level.path, f.progress);
      var cls = classMap[f.cls] || {icon:'🔥', letter:'?'};
      var col = classColour(f.cls);
      var hc = contrastEnabled;
      var reacting = f.reaction && performance.now() < (f.reactionUntil||0);
      var s = 26, x = p[0], y = p[1];                 // s stays the layout unit for badge/icon/rings
      var fs = s * 1.9;                                // flame size — roughly double, CHARACTER only
      var baseY = y + s*0.55;                          // base anchor line on the path
      var tt = performance.now()*0.001;
      var ph = (f.id||0)*1.7;                          // per-fire phase (no lockstep)
      // ITEM-041 + ITEM-051 merged: the fire visibly RESISTS being worn down — the
      // flame character shrinks toward the kill as hp drops (greyscale/hc-safe: a
      // size cue, not a colour cue), plus a dashed amber "resisting" ring. Adam's
      // ITEM-051 bigger, base-anchored flame (fs) is the full-health size; it scales
      // down with remaining hp while the base stays anchored on the path.
      var hpFrac = (f.hp===undefined) ? 1 : Math.max(0, Math.min(1, f.hp));
      var flameScale = fs * (0.62 + 0.38*hpFrac);      // shrinks as the fire is worn down
      if (hpFrac < 0.999 && hpFrac > 0){
        ctx.setLineDash([3,3]); ctx.beginPath(); ctx.arc(x, baseY - fs*0.6, fs*0.9, 0, Math.PI*2);
        ctx.strokeStyle = hc ? '#fde68a' : '#d97706'; ctx.lineWidth=2; ctx.stroke(); ctx.setLineDash([]);
      }
      // reaction rings — KEEP the exact shapes (solid red = danger, dashed grey = useless), recentred on the taller flame
      if (reacting && f.reaction==='danger'){
        ctx.beginPath(); ctx.arc(x,baseY - fs*0.6,fs*1.05,0,Math.PI*2); ctx.strokeStyle='#b91c1c'; ctx.lineWidth=4; ctx.stroke();
      } else if (reacting && f.reaction==='useless'){
        ctx.setLineDash([4,4]); ctx.beginPath(); ctx.arc(x,baseY - fs*0.6,fs*1.0,0,Math.PI*2); ctx.strokeStyle='#9ca3af'; ctx.lineWidth=3; ctx.stroke(); ctx.setLineDash([]);
      }
      // the distinctive animated character (per type) — Adam's enlarged base-anchored
      // flame, scaled down by remaining hp (ITEM-041) so it shrinks as it goes out.
      ctx.save(); ctx.translate(x, baseY - flameScale*0.72);
      drawFireCharacter(ctx, f.cls, flameScale, col, tt, ph, hc);
      ctx.restore();
      // letter badge (white circle + dark letter) — survives greyscale, KEPT size (from s), moved clear of the tall flame
      ctx.fillStyle='#fff'; ctx.strokeStyle='rgba(0,0,0,.18)'; ctx.lineWidth=1;
      ctx.beginPath(); ctx.arc(x+fs*0.62,baseY - fs*1.15,s*0.42,0,Math.PI*2); ctx.fill(); ctx.stroke();
      ctx.fillStyle='#101418'; ctx.font='700 '+(s*0.62)+'px system-ui'; ctx.textAlign='center'; ctx.textBaseline='middle';
      ctx.fillText(cls.letter||'?', x+fs*0.62, baseY - fs*1.15);
      // class icon below the burning object — KEPT
      ctx.font=(s*0.7)+'px system-ui'; ctx.fillStyle='#101418'; ctx.fillText(cls.icon||'🔥', x, baseY + s*1.0);
      // danger warning glyph above the taller flame tip — KEPT
      if (reacting && f.reaction==='danger'){ ctx.font='15px system-ui'; ctx.fillText('⚠️', x, baseY - fs*1.72 - 12); }
      ctx.textBaseline='alphabetic';
    }
    function drawOverlay(){
      // Just a soft dim when the level is over; the detailed recap is an HTML modal.
      if (!game || game.status==='playing' || game.status==='idle') return;
      ctx.fillStyle = contrastEnabled ? 'rgba(11,13,18,.55)' : 'rgba(244,247,252,.55)';
      ctx.fillRect(0,0,canvas.width,canvas.height);
    }

    // --- Reward vignettes + finale (ITEM-028) ---------------------------------
    // A tiny, self-contained canvas animation engine. Everything is guarded: if a
    // scene ever throws, the loop stops and the game keeps working (optional-feature
    // rule). Pure canvas/JS, no libraries.
    function updateAntonMood(){
      var el=document.getElementById('antonMood'); if (!el) return;
      if (!antonArc || !antonArc.length){ el.textContent=''; return; }
      var i=Math.max(0, Math.min(antonArc.length-1, campaignProgress));
      el.textContent='👻 ' + antonArc[i];
    }
    function stopVignetteAnim(){ if (vigRAF){ try { cancelAnimationFrame(vigRAF); } catch(e){} vigRAF=null; } }
    function runSceneLoop(canvasId, sceneName){
      var cv=document.getElementById(canvasId); if (!cv) return;
      var c=null; try { c=cv.getContext('2d'); } catch(e){ return; }
      if (!c) return;
      var start=performance.now();
      stopVignetteAnim();
      function step(now){
        var t=(now-start)/1000;
        try {
          c.clearRect(0,0,cv.width,cv.height);
          drawScene(c, cv.width, cv.height, t, sceneName);
        } catch(e){ stopVignetteAnim(); return; }   // never crash the page
        vigRAF=requestAnimationFrame(step);
      }
      vigRAF=requestAnimationFrame(step);
    }
    // Gentle, fictional scenes — soft motion only, no real names/events.
    function drawScene(c, w, h, t, name){
      if (name==='lantern'){
        // a warm lantern glow drifting up a dark half-timbered lane
        c.fillStyle='#0b0704'; c.fillRect(0,0,w,h);
        c.fillStyle='#1c140c';
        c.fillRect(0,0,w*0.22,h); c.fillRect(w*0.78,0,w*0.22,h);
        c.strokeStyle='rgba(120,80,40,.5)'; c.lineWidth=3;
        for (var i=1;i<5;i++){ c.beginPath(); c.moveTo(0,h*i/5); c.lineTo(w*0.22,h*i/5 - 18); c.stroke();
          c.beginPath(); c.moveTo(w*0.78,h*i/5-18); c.lineTo(w,h*i/5); c.stroke(); }
        var gy=h-40 - (t*26)%(h+30);
        var gr=c.createRadialGradient(w/2,gy,2, w/2,gy,46);
        gr.addColorStop(0,'rgba(255,214,140,.95)'); gr.addColorStop(1,'rgba(255,180,80,0)');
        c.fillStyle=gr; c.beginPath(); c.arc(w/2,gy,46,0,Math.PI*2); c.fill();
        c.fillStyle='#ffcf87'; c.beginPath(); c.arc(w/2,gy,6,0,Math.PI*2); c.fill();
        // neighbours passing buckets (dots bobbing)
        for (var b=0;b<5;b++){ var bx=w*0.30+b*w*0.1; var by=h-24+Math.sin(t*2+b)*4;
          c.fillStyle='#e7c9a0'; c.beginPath(); c.arc(bx,by,5,0,Math.PI*2); c.fill(); }
      } else if (name==='records'){
        // parchment ledger, a highlight sweeps down and reveals a shimmering name
        c.fillStyle='#efe2c6'; c.fillRect(0,0,w,h);
        c.strokeStyle='rgba(90,70,40,.5)'; c.lineWidth=2;
        var lineY; for (var r=0;r<9;r++){ lineY=24+r*20; c.beginPath(); c.moveTo(30,lineY); c.lineTo(w-30, lineY); c.stroke(); }
        var nameY=24+4*20;
        var sweep=(t*40)%(h+40);
        c.fillStyle='rgba(255,240,180,.25)'; c.fillRect(0, sweep-16, w, 22);
        var glow=Math.max(0, Math.sin(t*1.5));
        c.globalAlpha=0.4+0.6*glow; c.strokeStyle='#b8860b'; c.lineWidth=3;
        c.beginPath(); c.moveTo(70, nameY); c.lineTo(w-120, nameY); c.stroke(); c.globalAlpha=1;
        c.fillStyle='rgba(184,134,11,'+(0.5+0.5*glow)+')'; c.font='italic 14px system-ui'; c.textAlign='left';
        c.fillText('… Anton, Wächter der Burg …', 74, nameY-5);
        drawGhost(c, w-70, h/2, 1.1, 0.7+0.25*glow, -0.05, false, glow>0.6);
      } else if (name==='storm'){
        // wind lines settle, stars come out, people gather safely below
        c.fillStyle='#0e1726'; c.fillRect(0,0,w,h);
        var calm=Math.min(1, t/3);
        c.strokeStyle='rgba(160,180,210,'+(0.5*(1-calm))+')'; c.lineWidth=2;
        for (var s=0;s<7;s++){ var yy=20+s*24+Math.sin(t*4+s)*6*(1-calm);
          c.beginPath(); c.moveTo(0,yy); c.lineTo(w*(0.5+0.5*(1-calm)), yy-10); c.stroke(); }
        for (var st=0; st<18; st++){ var sx=(st*53%w), sy=(st*29%(h*0.6));
          c.globalAlpha=calm*(0.4+0.6*Math.abs(Math.sin(t+st))); c.fillStyle='#fde68a';
          c.beginPath(); c.arc(sx,sy,1.5,0,Math.PI*2); c.fill(); }
        c.globalAlpha=1;
        c.fillStyle='#14532d'; c.beginPath(); c.arc(w*0.2,h-30,22,0,Math.PI*2); c.fill();
        c.fillStyle='#7a5230'; c.fillRect(w*0.2-4,h-26,8,20);
        for (var p=0;p<6;p++){ var px=w*0.45+p*24, py=h-22+Math.sin(t*1.5+p)*2;
          c.fillStyle='#cbd5e1'; c.beginPath(); c.arc(px,py,5,0,Math.PI*2); c.fill(); }
      } else if (name==='festival'){
        // night sky, gentle rising fireworks bursting, a warm crowd below
        c.fillStyle='#0a0614'; c.fillRect(0,0,w,h);
        for (var f=0; f<3; f++){
          var period=2.4, phase=(t + f*0.8)%period, cx=w*(0.25+0.25*f), topY=h*0.25+f*10;
          if (phase<1.0){ var ry=h-20-(h*0.7)*phase; c.fillStyle='#fca5a5';
            c.beginPath(); c.arc(cx,ry,2,0,Math.PI*2); c.fill(); }
          else { var br=(phase-1.0)*70, al=Math.max(0,1-(phase-1.0)/1.4);
            c.strokeStyle='rgba(253,224,120,'+al+')'; c.lineWidth=2;
            for (var a=0;a<10;a++){ var ang=a*Math.PI/5;
              c.beginPath(); c.moveTo(cx,topY); c.lineTo(cx+Math.cos(ang)*br, topY+Math.sin(ang)*br); c.stroke(); } }
        }
        for (var q=0;q<10;q++){ var qx=20+q*w*0.096, qy=h-16+Math.sin(t*2+q)*2;
          c.fillStyle='#e7c9a0'; c.beginPath(); c.arc(qx,qy,4,0,Math.PI*2); c.fill(); }
      } else if (name==='helmet'){
        // the community gathers and gives Anton the fire helmet, then he rises brighter
        c.fillStyle='#0a0614'; c.fillRect(0,0,w,h);
        var cx=w/2, cy=h*0.6;
        for (var d=0; d<14; d++){ var ang=d*(Math.PI*2/14), rr=Math.min(w,h)*0.42;
          var dx=cx+Math.cos(ang)*rr, dy=cy+Math.sin(ang)*rr*0.7 + Math.sin(t*1.4+d)*2;
          c.fillStyle='#c7b8e6'; c.beginPath(); c.arc(dx,dy,5,0,Math.PI*2); c.fill(); }
        var settle=Math.min(1, t/2.2);
        var bright=0.7+0.3*Math.min(1,Math.max(0,(t-2.2)/1.5));
        drawGhost(c, cx, cy, 1.6, 0.6+0.4*settle, (1-settle)*0.1, settle>=1, bright>0.9);
        if (settle<1){  // helmet descending onto his head
          var hy=cy-70 - (1-settle)* (h*0.35);
          c.save(); c.translate(cx, hy); c.rotate(-0.2); c.fillStyle='#dc2626';
          c.fillRect(-21,-3,42,8); c.beginPath(); c.arc(0,0,13,Math.PI,0); c.fill(); c.restore();
        }
        if (bright>0.9){ for (var k=0;k<8;k++){ var ka=t*2+k, kr=30+ (t*20)%40;
          c.globalAlpha=Math.max(0,1-((t*20)%40)/40); c.fillStyle='#fde68a';
          c.beginPath(); c.arc(cx+Math.cos(ka)*kr, cy-30+Math.sin(ka)*kr*0.6, 2,0,Math.PI*2); c.fill(); }
          c.globalAlpha=1; }
      }
    }
    function openVignette(vig, thenFinale){
      vignetteThenFinale = !!thenFinale;
      try {
        document.getElementById('vigTitle').textContent = (vig && vig.title) || '';
        document.getElementById('vigCaption').textContent = (vig && vig.caption) || '';
        document.getElementById('vignette').style.display='flex';
        runSceneLoop('vigCanvas', (vig && vig.scene) || 'lantern');
      } catch(e){
        stopVignetteAnim();
        var v=document.getElementById('vignette'); if (v) v.style.display='none';
        if (vignetteThenFinale){ vignetteThenFinale=false; openFinale(); } else showRecap();
      }
    }
    function closeVignette(){
      stopVignetteAnim();
      var v=document.getElementById('vignette'); if (v) v.style.display='none';
      if (vignetteThenFinale){ vignetteThenFinale=false; openFinale(); } else showRecap();
    }
    function openFinale(){
      var fin = antonFinale || {};
      try {
        document.getElementById('finTitle').textContent = fin.title || 'Finale';
        document.getElementById('finCaption').textContent = fin.caption || '';
        var box=document.getElementById('finLines'); box.innerHTML='';
        (fin.lines || []).forEach(function(ln){
          var p=document.createElement('p'); p.textContent=ln; p.style.margin='.4rem 0'; box.appendChild(p);
        });
        document.getElementById('finale').style.display='flex';
        runSceneLoop('finCanvas', fin.scene || 'helmet');
      } catch(e){
        stopVignetteAnim();
        var el=document.getElementById('finale'); if (el) el.style.display='none';
        showRecap();
      }
    }
    function closeFinale(){
      stopVignetteAnim();
      var el=document.getElementById('finale'); if (el) el.style.display='none';
      showRecap();
    }
    // Decide what plays when a level ends (ITEM-028): a campaign WIN unlocks its reward
    // vignette (then the finale if the whole campaign is now complete), then the recap.
    function handleEnd(){
      if (!game) return;
      var won = game.status==='won';
      var completedCampaign=false;
      if (won && isCampaign && missionNo){
        if (missionNo>campaignProgress){ campaignProgress=missionNo; saveProgress(); renderLevelBar(); updateAntonMood(); }
        completedCampaign = (campaignTotal()>0 && campaignProgress>=campaignTotal());
      }
      if (won && isCampaign && level && level.vignette && level.vignette.scene){
        openVignette(level.vignette, completedCampaign);
      } else if (won && completedCampaign){
        openFinale();
      } else {
        showRecap();
      }
    }

    function showRecap(){
      if (!game) return;
      var total=game.schedule.length, handled=game.ext;
      var knowledge = total ? Math.round(100*handled/total) : 0;
      document.getElementById('recapTitle').textContent =
        game.status==='won' ? tr('recap_won') : tr('recap_lost');
      document.getElementById('recapTitle').style.color = game.status==='won' ? '#15803d' : '#b91c1c';
      document.getElementById('recapScore').textContent = tr('recap_score') + knowledge + '%';
      document.getElementById('recapLine').textContent =
        handled + tr('recap_of') + total + tr('recap_ok') + game.leaked +
        tr('recap_through') + (game.danger+game.useless) + tr('recap_mistakes');
      var rows='';
      var seen={};
      game.schedule.forEach(function(ev){
        if (seen[ev['class']]) return; seen[ev['class']]=true;
        var c=classMap[ev['class']]||{};
        rows += '<div style="display:flex; align-items:center; gap:.5rem; padding:.25rem 0; border-top:1px solid var(--line);">' +
                '<span style="font-size:1.3rem;">'+(c.icon||'🔥')+'</span>' +
                '<span style="flex:1;">'+(c.name_de||ev['class'])+'</span>' +
                '<span style="color:var(--c);">'+tr('recap_correct')+(rightActionFor(ev['class'])||'')+'</span></div>';
      });
      document.getElementById('recapClasses').innerHTML =
        '<div style="color:var(--muted); margin-bottom:.2rem;">'+tr('recap_these_fires')+'</div>' + rows;

      // Anton closes the mission and notes the rescue bonus. (Campaign progress is
      // already advanced in handleEnd(), before the reward vignette/finale plays.)
      var antonEl=document.getElementById('recapAnton');
      var nextBtn=document.getElementById('recapNext');
      antonEl.textContent=''; nextBtn.style.display='none';
      if (isCampaign && antonLines){
        var msg = '';
        if (game.status==='won'){
          msg = antonLines.close || '';
          if (game.leaked===0 && antonLines.bonus) msg += (msg ? '  ' : '') + '⭐ ' + antonLines.bonus;
        } else {
          // Never scold: a gentle, encouraging word on a loss.
          msg = tr('recap_loss_anton');
        }
        if (msg) antonEl.textContent = '👻 ' + msg;
        if (game.status==='won' && missionNo){
          var nxt=null;
          levelsMeta.forEach(function(l){ if (l.campaign && l.mission===missionNo+1) nxt=l; });
          if (nxt && missionUnlocked(nxt.mission)){
            nextBtn.style.display='';
            nextBtn.textContent=tr('recap_next');
            nextBtn.onclick=function(){ document.getElementById('recap').style.display='none'; loadLevel(nxt.index); };
          }
        }
      }
      document.getElementById('recap').style.display='flex';
    }

    function buildLib(){
      var body=document.getElementById('libBody'); if (!body) return;
      var rows='';
      (window._classOrder||[]).forEach(function(cid){
        var c=classMap[cid]||{};
        var goods=[], dangers=[];
        (toolsList||[]).forEach(function(t){
          var o=matrixMap[cid+'|'+t.id];
          if (o==='good') goods.push(t.short);
          else if (o==='danger') dangers.push(t.short);
        });
        rows += '<div style="padding:.5rem 0; border-top:1px solid var(--line);">' +
          '<div style="font-weight:600;">'+(c.icon||'🔥')+' '+(c.name_de||cid)+'</div>' +
          '<div style="color:var(--ink);">'+(c.card_de||'')+'</div>' +
          '<div style="color:var(--c);">'+tr('lib_correct')+(goods.join(', ')||'—')+'</div>' +
          (dangers.length ? '<div style="color:var(--red);">'+tr('lib_dangerous')+dangers.join(', ')+'</div>' : '') +
          '</div>';
      });
      body.innerHTML = rows || '<p>'+tr('lib_loading')+'</p>';
    }
    function openLib(){ buildLib(); if (game && game.status==='playing') paused=true; document.getElementById('lib').style.display='flex'; }
    function closeLib(){ document.getElementById('lib').style.display='none'; paused=false; last=performance.now(); }

    // --- game logic (mirrors the server's GameState) ---
    function firePos(f){ return pathPointAt(game.level.path, f.progress); }
    function nearestFireInRange(tw){
      var bx=tw.spot[0], by=tw.spot[1], best=null, bestD=null;
      for (var i=0;i<game.fires.length;i++){
        var p=firePos(game.fires[i]); var d=Math.hypot(p[0]-bx, p[1]-by);
        if (d<=TOWER_RANGE && (bestD===null || d<bestD)){ best=game.fires[i]; bestD=d; }
      }
      return best;
    }
    function advance(dt){
      var g = game; if (!g || g.status!=='playing') return;
      g.elapsed += dt;
      // spawn (schedule comes from the server; key is "class")
      while (g.spawned < g.schedule.length && g.schedule[g.spawned].t <= g.elapsed){
        var scls = g.schedule[g.spawned]["class"];
        var shaz = HAZARD_CLASS_OF_IN(g, scls);
        if (shaz && g.supplies[shaz]==='off'){
          // its supply is already cut — this fire never really starts (counted handled)
          g.ext++; g.spawned++; continue;
        }
        g.fires.push({id:g.nextId++, cls:scls, progress:0, hp:FIRE_HP}); g.spawned++;
      }
      // towers fire at the nearest fire in range; the outcome depends on the matrix
      for (var ti=0; ti<g.towers.length; ti++){
        var tw=g.towers[ti]; tw.cooldown-=dt;
        if (tw.cooldown>0) continue;
        var target=nearestFireInRange(tw);
        if (!target) continue;
        tw.cooldown = TOWER_COOLDOWN;
        var tp=firePos(target);
        sprays.push({x1:tw.spot[0], y1:tw.spot[1], x2:tp[0], y2:tp[1], until:performance.now()+120});
        var thaz = HAZARD_CLASS_OF_IN(g, target.cls);
        if (thaz && g.supplies[thaz]==='on'){
          // supply still on: spraying does nothing — cut the supply first. ITEM-040:
          // a shot that plainly can't touch this fire never spends any charge.
          target.reaction='useless'; target.reactionUntil=performance.now()+500;
          showFeedback(hazardWarn(thaz), 'danger');
          playSound('danger');
          g.useless++;
          continue;
        }
        var outcome = matrixMap[target.cls + '|' + tw.tool];
        if (outcome==='good' || outcome==='weak'){
          // ITEM-040: this shot actually discharged at the fire, so it costs a charge.
          // ITEM-041: it wears the fire's resistance down — "good" clears it in one
          // hit, "weak" needs another — and the reward + smart bonus are only paid
          // out on the actual put-out.
          tw.charge--;
          var dmg = (outcome==='good') ? GOOD_HIT_DAMAGE : WEAK_HIT_DAMAGE;
          target.hp = (target.hp===undefined ? FIRE_HP : target.hp) - dmg;
          if (target.hp <= 1e-9){
            g.fires = g.fires.filter(function(f){ return f.id!==target.id; });
            g.budget += EXTINGUISH_REWARD + (outcome==='good' ? SMART_BONUS : 0); updateBudget();
            g.ext++;
          } else {
            target.reaction='hit'; target.reactionUntil=performance.now()+400;
          }
          playSound('good');
        } else if (outcome==='danger'){
          // ITEM-040: a dangerous mismatch DID discharge the extinguisher (badly),
          // so it costs a charge too — the wrong choice is never cheaper.
          tw.charge--;
          target.progress = Math.min(0.999, target.progress + DANGER_SPEEDUP);
          target.reaction='danger'; target.reactionUntil=performance.now()+500;
          showFeedback(reasonMap[target.cls + '|' + tw.tool], 'danger');
          playSound('danger');
          g.danger++;
          // ITEM-034: water on a liquid/cooking-oil fire can split it in two.
          if (tw.tool==='water' && (target.cls==='B' || target.cls==='F') && g.fires.length < MAX_ACTIVE_FIRES){
            g.fires.push({id:g.nextId++, cls:target.cls, progress:Math.max(0, target.progress-0.05), hp:FIRE_HP});
          }
        } else {
          // Useless tool: nothing happens, the shot is wasted, no budget, and
          // (ITEM-040) no charge.
          target.reaction='useless'; target.reactionUntil=performance.now()+500;
          showFeedback(reasonMap[target.cls + '|' + tw.tool], 'useless');
          playSound('useless');
          g.useless++;
        }
      }
      // ITEM-040: a tower with no charge left is spent — remove it, freeing the spot.
      g.towers = g.towers.filter(function(tw){ return tw.charge > 0; });
      // move fires; arrivals cost a life
      var still=[];
      for (var i=0;i<g.fires.length;i++){
        var f=g.fires[i]; f.progress += g.speed*dt;
        if (f.progress>=1){ g.lives--; g.leaked++; g.flashUntil=performance.now()+350; } else still.push(f);
      }
      g.fires=still;
      if (g.lives<=0){ g.lives=0; g.status='lost'; if (!g.fledAt) g.fledAt=performance.now(); return; }
      if (g.spawned>=g.schedule.length && g.fires.length===0){ g.status='won'; }
    }

    // A fresh game for a level: 'idle' until "Einsatz starten". Towers can be
    // placed while idle (build first) and while playing.
    function newGame(lv){
      var sup={}; (lv.supplies||[]).forEach(function(h){ sup[h]='on'; });
      return { level:lv, schedule:(lv.schedule||[]),
               speed: FIRE_PX_PER_SEC / pathLength(lv.path),
               lives: lv.building.lives, budget: lv.budget||0,
               elapsed:0, spawned:0, fires:[], nextId:0,
               towers:[], nextTowerId:0, status:'idle', flashUntil:0, fledAt:0,
               ext:0, danger:0, useless:0, leaked:0, supplies:sup };
    }
    function onStartButton(){
      initAudio();   // first real user gesture — unlock/resume audio (autoplay-safe)
      if (!game) return;
      if (game.status==='idle'){ game.status='playing'; last=performance.now(); }
      else if (game.status==='won' || game.status==='lost'){
        game=newGame(level); sprays=[]; hintShown=false; seen={}; prevStatus='idle';
      }
      updateControls(); updateBudget();
    }

    function towerAt(idx){
      if (!game) return null;
      for (var i=0;i<game.towers.length;i++) if (game.towers[i].spot_index===idx) return game.towers[i];
      return null;
    }
    function placeTower(spotIndex, toolId){
      if (!game || !level) return false;
      var spots=level.build_spots;
      if (spotIndex<0 || spotIndex>=spots.length) return false;
      if (towerAt(spotIndex)) return false;                 // spot taken
      var cost=(toolMap[toolId]||{}).cost||0;
      if (cost<=0 || game.budget<cost) return false;        // can't afford
      game.budget-=cost;
      var charge=towerChargeFor(level);
      game.towers.push({id:game.nextTowerId++, spot_index:spotIndex, spot:spots[spotIndex], tool:toolId,
                         cooldown:0, charge:charge, maxCharge:charge});   // ITEM-040
      updateBudget();
      return true;
    }
    // ITEM-042: switch off / remove a (possibly wrongly-placed) extinguisher, freeing
    // its spot. NO REFUND — spent money is gone, on purpose, so removal can never be
    // used to cheese a win by recycling budget. A distinct path from placeTower (see
    // boardPlaceAt / the keyboard handler) so the one-tap-one-tower placement
    // guarantee is never touched.
    function removeTower(spotIndex){
      if (!game) return false;
      var before=game.towers.length;
      game.towers = game.towers.filter(function(tw){ return tw.spot_index!==spotIndex; });
      var removed = game.towers.length < before;
      if (removed){ showFeedback(tr('tower_removed'), 'ok'); updateBudget(); }
      return removed;
    }

    // Cut a supply (ITEM-016): puts out the fires it fed and stops them being a threat.
    function shutOff(hazard){
      var g=game; if (!g || !g.supplies || g.supplies[hazard]!=='on') return;
      if (g.status==='won' || g.status==='lost') return;
      g.supplies[hazard]='off';
      var cls=HAZARD_CLASS[hazard];
      var out=g.fires.filter(function(f){ return f.cls===cls; });
      if (out.length){
        g.fires=g.fires.filter(function(f){ return f.cls!==cls; });
        for (var i=0;i<out.length;i++){ g.ext++; g.budget+=EXTINGUISH_REWARD; }
        updateBudget();
      }
      if (g.status==='playing' && g.spawned>=g.schedule.length && g.fires.length===0){ g.status='won'; }
      showFeedback(hazard==='gas' ? tr('gas_off') : tr('power_off'), 'ok');
      renderHazardControls();
    }

    // The "cut the supply" buttons a level offers (only the hazards it declares).
    function renderHazardControls(){
      var bar=document.getElementById('hazardControls'); if (!bar) return;
      bar.innerHTML='';
      var sup=(level && level.supplies) || [];
      sup.forEach(function(h){
        var btn=document.createElement('button');
        var off = game && game.supplies && game.supplies[h]==='off';
        var over = game && (game.status==='won' || game.status==='lost');
        btn.textContent = hazardButton(h) + (off ? ' ✓' : '');
        btn.disabled = off || over;
        btn.onclick = function(){ shutOff(h); };
        bar.appendChild(btn);
      });
    }

    function updateBudget(){
      var b = game ? game.budget : (level ? (level.budget||0) : 0);
      document.getElementById('budget').textContent = '💰 ' + b;
      Array.prototype.forEach.call(document.querySelectorAll('#toolPalette .toolbtn'), function(btn){
        var cost=parseInt(btn.getAttribute('data-cost'),10);
        btn.disabled = (b < cost);
        btn.classList.toggle('active', btn.getAttribute('data-tool')===selectedTool);
      });
    }

    // Two-tone flat extinguisher in the tool's colour, with its short label.
    function drawTower(tw){
      var t=toolMap[tw.tool]||{hex:'#334155', short:'?'};
      var x=tw.spot[0], y=tw.spot[1];
      ctx.beginPath(); ctx.arc(x,y,TOWER_RANGE,0,Math.PI*2); ctx.fillStyle='rgba(47,111,237,.05)'; ctx.fill();
      // ITEM-055: the placed extinguisher is drawn 50% bigger (26x36 -> 39x54).
      // Only the DRAWING grows — the build-spot position and the tap/keyboard hit
      // area (nearestSpot / HIT_RADIUS) are unchanged, so placement is unaffected.
      var w=39, h=54;
      drawExtShape(ctx, x-w/2, y-h/2+3, w, h, toolColour(t.hex));
      ctx.fillStyle='#101418'; ctx.font='700 12px system-ui'; ctx.textAlign='center'; ctx.textBaseline='middle';
      ctx.fillText((t.short||'').slice(0,6), x, y+h*0.27);
      ctx.textBaseline='alphabetic';
      // ITEM-054 (moves ITEM-040's gauge): a shrinking charge gauge standing
      // VERTICALLY to the RIGHT of the extinguisher — full at the top, draining
      // downward as it fires — instead of a horizontal bar underneath. The FILL
      // LENGTH is the cue (greyscale/hc-safe, not colour alone); it turns a second,
      // distinct shade once low so it also reads without colour vision.
      var maxC = tw.maxCharge || tw.charge || 1;
      var frac = Math.max(0, Math.min(1, tw.charge / maxC));
      var gw=6, gh=h*0.82, gx=x + w/2 + 4, gy=(y - h/2 + 3) + (h - gh)/2;
      ctx.strokeStyle = contrastEnabled ? '#e5e7eb' : '#1f2937'; ctx.lineWidth=1;
      ctx.strokeRect(gx, gy, gw, gh);
      var low = frac <= 0.34;
      ctx.fillStyle = low ? (contrastEnabled?'#fca5a5':'#b91c1c') : (contrastEnabled?'#bbf7d0':'#15803d');
      var fillH = Math.max(0,(gh-2)*frac);
      ctx.fillRect(gx+1, gy+1+((gh-2)-fillH), gw-2, fillH);
    }
    function drawSprays(){
      var now=performance.now(), keep=[];
      for (var i=0;i<sprays.length;i++){ var s=sprays[i]; if (s.until<now) continue; keep.push(s);
        ctx.strokeStyle='rgba(255,255,255,.85)'; ctx.lineWidth=3;
        ctx.beginPath(); ctx.moveTo(s.x1,s.y1); ctx.lineTo(s.x2,s.y2); ctx.stroke();
      }
      sprays=keep;
    }

    function setLives(n){ var el=document.getElementById('lives'); if (el) el.textContent=''; }   // ITEM-058: on-screen lives counter removed — the house condition is the life gauge
    function currentWave(){ if (!game || !game.spawned) return 0; return game.schedule[game.spawned-1].wave + 1; }
    function totalWaves(){ return level && level.waves ? level.waves.length : 0; }
    function infoText(){
      if (!game || game.status==='idle') return totalWaves() + tr('info_waves');
      if (game.status==='won') return tr('info_won');
      if (game.status==='lost') return tr('info_lost');
      return tr('info_wave') + currentWave() + ' / ' + totalWaves() + ' · ' + game.fires.length + tr('info_fires');
    }
    function updateControls(){
      var btn=document.getElementById('startBtn');
      if (!game || game.status==='idle'){ btn.textContent=tr('btn_start'); btn.disabled=false; }
      else if (game.status==='playing'){ btn.textContent=tr('btn_running'); btn.disabled=true; }
      else { btn.textContent=tr('btn_restart'); btn.disabled=false; }
      renderHazardControls();
    }

    // One shared, styled two-tone flat background (sky gradient + a couple of simple
    // flat props). Per-mission distinct locations are a later item (ITEM-035), not here.
    // --- ITEM-035: per-mission location background --------------------------------
    // One soft per-level sky/wash gradient (computed ONCE, cached per level+size) plus
    // a few LOW-CONTRAST flat silhouette props that evoke the place. In high-contrast
    // mode the background becomes a plain dark field so it never hurts readability.
    var BG_STOPS = {
      fachwerk:   ['#e8eef7','#f6efe2'],   // pale day sky over the old lane
      bibliothek: ['#efe3c8','#e7d6b6'],   // warm amber library interior
      kurpark:    ['#8ea0b4','#c6d2de'],   // grey storm sky
      feuerwerk:  ['#241d47','#3a2f5e'],   // festival night
      schlosserei:['#d7dde5','#c3ccd6']    // cool grey workshop
    };
    var _bgGrad=null, _bgKey='';
    function bgGradient(w,h,key){
      var k=(key||'')+'|'+w+'x'+h;
      if (k!==_bgKey){
        var g=ctx.createLinearGradient(0,0,0,h);
        var st=BG_STOPS[key]||['#e6effb','#f6f9fd'];
        g.addColorStop(0,st[0]); g.addColorStop(1,st[1]);
        _bgGrad=g; _bgKey=k;
      }
      return _bgGrad;
    }
    function bgFachwerk(w,h){                     // a row of half-timbered houses, top
      for (var i=0;i<4;i++){ var x=30+i*235, y=18, bw=150, bh=86;
        ctx.fillStyle='#e6d7c0'; rr(ctx,x,y,bw,bh,4); ctx.fill();
        ctx.fillStyle='#b06a4a'; ctx.beginPath(); ctx.moveTo(x-8,y); ctx.lineTo(x+bw/2,y-24); ctx.lineTo(x+bw+8,y); ctx.closePath(); ctx.fill();
        ctx.strokeStyle='#8a6b4a'; ctx.lineWidth=3;
        ctx.strokeRect(x+3,y+3,bw-6,bh-6);
        ctx.beginPath(); ctx.moveTo(x+3,y+3); ctx.lineTo(x+bw-3,y+bh-3); ctx.moveTo(x+bw-3,y+3); ctx.lineTo(x+3,y+bh-3); ctx.stroke(); }
    }
    function bgBibliothek(w,h){                   // a bookshelf band + a stone arch, top
      ctx.fillStyle='#9a7b58'; rr(ctx,20,14,w-40,84,6); ctx.fill();
      var cols=['#b0563a','#3f6ea8','#6b8a4a','#9a6a3a','#7c5aa0'];
      for (var b=0;b*20<w-56;b++){ ctx.fillStyle=cols[b%5]; ctx.fillRect(30+b*20,22,15,68); }
      ctx.fillStyle='#7a6142'; ctx.fillRect(20,90,w-40,10);
      ctx.strokeStyle='#b79b74'; ctx.lineWidth=6; ctx.beginPath(); ctx.arc(w/2,116,140,Math.PI,0); ctx.stroke();
    }
    function bgKurpark(w,h){                      // storm clouds + trees + faint rain
      ctx.fillStyle='#8493a5';
      for (var i=0;i<4;i++){ var cx=90+i*250; ctx.beginPath(); ctx.arc(cx,46,40,0,Math.PI*2); ctx.arc(cx+42,58,30,0,Math.PI*2); ctx.arc(cx-40,58,26,0,Math.PI*2); ctx.fill(); }
      [w*0.14, w*0.86].forEach(function(tx){ var ty=150;
        ctx.fillStyle='#8a6238'; rr(ctx,tx-6,ty,12,34,3); ctx.fill();
        ctx.fillStyle='#6f9a5a'; ctx.beginPath(); ctx.arc(tx,ty-8,30,0,Math.PI*2); ctx.fill(); });
      ctx.strokeStyle='rgba(150,175,200,.5)'; ctx.lineWidth=1.5;
      for (var r=0;r<26;r++){ var rx=(r*47)%w, ry=(r*83)%(h*0.55); ctx.beginPath(); ctx.moveTo(rx,ry); ctx.lineTo(rx-6,ry+14); ctx.stroke(); }
    }
    function bgFeuerwerk(w,h){                    // night sky: stars, bunting, soft beams
      ctx.fillStyle='rgba(255,255,255,.75)';
      for (var s=0;s<28;s++){ ctx.fillRect((s*71)%w, (s*53)%(h*0.5), 2, 2); }
      var cols=['#e4572e','#f59e0b','#2f6fed','#14b8a6','#d6409f'];
      ctx.strokeStyle='#cfd6e0'; ctx.lineWidth=2; ctx.beginPath(); ctx.moveTo(0,26); ctx.lineTo(w,26); ctx.stroke();
      for (var i=0;i*44<w;i++){ var bx=i*44+12; ctx.fillStyle=cols[i%5];
        ctx.beginPath(); ctx.moveTo(bx-10,27); ctx.lineTo(bx+10,27); ctx.lineTo(bx,45); ctx.closePath(); ctx.fill(); }
      ctx.fillStyle='rgba(255,240,180,.10)';
      ctx.beginPath(); ctx.moveTo(w*0.3,0); ctx.lineTo(w*0.16,h); ctx.lineTo(w*0.42,h); ctx.closePath(); ctx.fill();
      ctx.beginPath(); ctx.moveTo(w*0.7,0); ctx.lineTo(w*0.58,h); ctx.lineTo(w*0.85,h); ctx.closePath(); ctx.fill();
    }
    function bgSchlosserei(w,h){                  // workshop: a window, a tool rack, a bench
      ctx.fillStyle='#c3ccd6'; rr(ctx,40,22,120,80,6); ctx.fill();
      ctx.strokeStyle='#8a97a6'; ctx.lineWidth=4; ctx.strokeRect(40,22,120,80);
      ctx.beginPath(); ctx.moveTo(100,22); ctx.lineTo(100,102); ctx.moveTo(40,62); ctx.lineTo(160,62); ctx.stroke();
      ctx.strokeStyle='#7a8494'; ctx.lineWidth=3; ctx.beginPath(); ctx.moveTo(w-230,40); ctx.lineTo(w-40,40); ctx.stroke();
      ctx.fillStyle='#8a97a6';
      ctx.fillRect(w-206,42,6,32); ctx.fillRect(w-212,72,18,8);            // hammer
      ctx.fillRect(w-150,42,4,38);                                          // driver
      ctx.lineWidth=4; ctx.strokeStyle='#8a97a6'; ctx.beginPath(); ctx.arc(w-100,58,13,0,Math.PI*1.4); ctx.stroke();  // wrench loop
      ctx.fillStyle='#9aa4b0'; ctx.fillRect(0,h-24,w,24);                   // workbench along the bottom
    }
    function drawBackground(){
      var w=canvas.width, h=canvas.height, key=level&&level.key;
      if (contrastEnabled){ ctx.fillStyle='#0b0d12'; ctx.fillRect(0,0,w,h); return; }  // plain dark field
      ctx.fillStyle=bgGradient(w,h,key); ctx.fillRect(0,0,w,h);
      ctx.save(); ctx.globalAlpha=0.5;                                       // low-contrast, decorative
      if (key==='fachwerk')       bgFachwerk(w,h);
      else if (key==='bibliothek')bgBibliothek(w,h);
      else if (key==='kurpark')   bgKurpark(w,h);
      else if (key==='feuerwerk') bgFeuerwerk(w,h);
      else if (key==='schlosserei')bgSchlosserei(w,h);
      ctx.restore();
    }
    // Draw Anton the ghost at (x,y) on any context. Shared by the board, the reward
    // vignettes and the finale so his look stays consistent. (ITEM-028)
    //   alpha = how solid he is, tilt = posture, helmet = wears the fire helmet,
    //   bright = a touch brighter + a small smile (braver).
    function drawGhost(c, x, y, scale, alpha, tilt, helmet, bright){
      c.save();
      c.translate(x, y); c.rotate(tilt||0); c.scale(scale, scale);
      var body = cssv('--blue') || '#2f6fed';
      c.globalAlpha = Math.max(0.2, Math.min(1, alpha));
      // TONE 1 — body (a touch brighter when braver)
      c.fillStyle = bright ? shade(body,0.12) : body;
      c.beginPath(); c.arc(0,0,18,Math.PI,0);
      c.lineTo(18,16);
      c.quadraticCurveTo(9,24, 0,16);
      c.quadraticCurveTo(-9,24, -18,16);
      c.closePath(); c.fill();
      // TONE 2 — lighter belly
      c.fillStyle = shade(body, 0.45);
      c.beginPath(); c.arc(0,2,11,Math.PI*0.15,Math.PI*0.85); c.fill();
      c.globalAlpha = Math.min(1, alpha+0.12);
      c.fillStyle='#fff';
      c.beginPath(); c.arc(-6,-2,4,0,Math.PI*2); c.arc(6,-2,4,0,Math.PI*2); c.fill();
      c.fillStyle='#101418';
      c.beginPath(); c.arc(-6,-1,2,0,Math.PI*2); c.arc(6,-1,2,0,Math.PI*2); c.fill();
      if (bright){  // a small confident smile
        c.strokeStyle='#101418'; c.lineWidth=1.5; c.beginPath(); c.arc(0,4,5,0.15*Math.PI,0.85*Math.PI); c.stroke();
      }
      if (helmet){  // the little crooked fire helmet — only from the finale onward
        c.save(); c.translate(0,-15); c.rotate(-0.2); c.globalAlpha=1; c.fillStyle=cssv('--red')||'#dc2626';
        c.fillRect(-13,-2,26,5); c.beginPath(); c.arc(0,0,8,Math.PI,0); c.fill(); c.restore();
      }
      c.restore();
    }
    function campaignTotal(){
      var n=0; levelsMeta.forEach(function(l){ if (l.campaign && l.mission) n++; }); return n;
    }
    // Anton grows braver with each completed mission (0..1).
    function antonBraveryFactor(){
      var tot = campaignTotal() || 4;
      return Math.max(0, Math.min(1, campaignProgress / tot));
    }
    // He only wears the helmet once the WHOLE campaign is complete (the finale gift).
    function antonWearsHelmet(){
      var tot = campaignTotal() || 4;
      return campaignProgress >= tot;
    }
    // ITEM-033: how worried Anton looks THIS level, driven by remaining lives (0 =
    // calm .. 1 = about to lose). Deliberately SEPARATE from antonBraveryFactor
    // (which tracks campaign/win progress across missions, not this level's
    // danger) — his win-side brave arc/helmet/finale are completely unaffected.
    function antonWorryFactor(){
      if (!game || !game.level || !game.level.building) return 0;
      var start = game.level.building.lives || 1;
      return 1 - Math.max(0, Math.min(1, game.lives / start));
    }
    function drawAnton(){
      var now=performance.now();
      var f=antonBraveryFactor();
      var worry=antonWorryFactor();
      // braver = rises up, stands more upright, more solid, a touch brighter.
      var x=canvas.width-44;
      var y=(54 - 14*f) + Math.sin(now/500)*(6 - 2*f);
      var alpha=0.5 + 0.45*f;
      var tilt=(1-f)*0.18 + Math.sin(now/900)*0.02;
      // ITEM-033: once the building has fallen (lives===0), Anton flees off-screen —
      // presentation only, the lose condition (lives<=0 in advance()) is unchanged.
      if (game && game.lives<=0 && game.fledAt){
        var since=(now-game.fledAt)/1000;
        y -= since*70; x += since*40;
        alpha = Math.max(0, alpha - since*0.5);
        tilt = -0.6 - since*0.3;
        if (alpha<=0) return;                 // fully flown off — nothing left to draw
        drawGhost(ctx, x, y, 1, alpha, tilt, antonWearsHelmet(), false);
        return;
      }
      // Worried: a lower, twitchier stance and a touch fainter the fewer lives
      // remain — additive with (not a replacement for) the bravery stance above.
      y += worry*10; tilt += worry*0.14 * Math.sin(now/220); alpha -= worry*0.15;
      drawGhost(ctx, x, y, 1, Math.max(0.15,alpha), tilt, antonWearsHelmet(), f>0.6);
    }
    // Anton "senses" the trouble and marks the spot where fire will break out
    // (ITEM-026): a gentle pulsing ring at the start of the path with a small note,
    // shown before the operation begins. Simple shapes in the game's own art style.
    function drawSense(wp){
      if (!wp || !wp.length) return;
      var now=performance.now();
      var x=wp[0][0], y=wp[0][1];
      var r=24 + Math.sin(now/300)*6;
      ctx.save();
      ctx.strokeStyle='rgba(180,83,9,.55)'; ctx.lineWidth=2;
      ctx.beginPath(); ctx.arc(x,y,r,0,Math.PI*2); ctx.stroke();
      ctx.beginPath(); ctx.arc(x,y,r*0.55,0,Math.PI*2); ctx.stroke();
      ctx.fillStyle='#b45309'; ctx.font='12px system-ui'; ctx.textAlign='left';
      ctx.fillText(tr('anton_senses'), x+r+4, y-2);
      ctx.restore();
    }

    function render(){
      if (!level) return;
      ctx.clearRect(0,0,canvas.width,canvas.height);
      drawBackground();
      drawPath(level.path);
      level.build_spots.forEach(function(s, idx){ var tw=towerAt(idx); if (tw) drawTower(tw); else drawBuildSpot(s[0],s[1]); });
      drawKeyHighlight();
      drawStart(level.path);
      // Before the operation starts, Anton marks where fire will break out.
      if (!game || game.status==='idle') drawSense(level.path);
      drawBuilding(level.building);
      drawAnton();
      if (game){
        game.fires.forEach(drawFire);
        drawSprays();
        setLives(game.lives);
        drawOverlay();
      } else {
        setLives(level.building.lives);
      }
      document.getElementById('info').textContent = infoText();
    }

    function showFeedback(msg, kind){
      if (!msg) return;
      var el=document.getElementById('feedback');
      el.textContent = (kind==='danger' ? '⚠️ ' : '') + 'Anton: ' + msg;
      el.style.color = (kind==='danger') ? 'var(--red)' : 'var(--muted)';
      feedbackUntil = performance.now() + 2600;
    }
    function showCard(cls){
      var c=classMap[cls]||{}; paused=true;
      // restore the top icon + static attribution for the "meet the fire" card
      // (the mission intro hides them and moves them to the bottom of its text).
      var attrib=document.getElementById('cardAttrib'); if (attrib) attrib.style.display='';
      document.getElementById('cardIcon').textContent = c.icon || '🔥';
      document.getElementById('cardTitle').textContent = (c.name_de||'') + (c.letter ? (' ('+c.letter+')') : '');
      document.getElementById('cardText').textContent = c.card_de || '';
      document.getElementById('card').style.display = 'flex';
    }
    // Anton opens a story mission (ITEM-026/027): he senses the trouble and tells a
    // short Königstein anecdote. One calm card at the start — reuses the existing
    // card modal so it doesn't stack extra pauses.
    function showMissionIntro(){
      if (!isCampaign || !antonLines || !antonLines.open) return;
      // ITEM-057: keep the top clear so the info text is easy to read on a short
      // landscape screen — no top icon, and the static attribution line is hidden
      // (its ghost + name are appended to the BOTTOM of the text below instead).
      document.getElementById('cardIcon').textContent = '';
      var attrib=document.getElementById('cardAttrib'); if (attrib) attrib.style.display='none';
      document.getElementById('cardTitle').textContent =
        (missionNo ? (tr('intro_mission') + missionNo + ' · ') : '') + (level ? level.name : '');
      var el=document.getElementById('cardText'); el.textContent='';
      var parts=[antonLines.open];
      if (antonLines.anecdote) parts.push(antonLines.anecdote);
      parts.forEach(function(p, idx){
        if (idx>0){ el.appendChild(document.createElement('br')); el.appendChild(document.createElement('br')); }
        el.appendChild(document.createTextNode(p));
      });
      // The ghost + "— Anton, der Burggeist" now sit at the bottom of the info text,
      // inside the scrollable region, so the reader reaches them after the anecdote.
      el.appendChild(document.createElement('br'));
      el.appendChild(document.createElement('br'));
      var g=document.createElement('span'); g.textContent='👻';
      g.style.fontSize='1.8rem'; g.style.display='block'; g.style.marginTop='.2rem';
      el.appendChild(g);
      var a=document.createElement('span'); a.textContent=tr('anton_attrib_inline');
      a.style.fontSize='.8rem'; a.style.color='var(--muted)'; a.style.display='block';
      el.appendChild(a);
      document.getElementById('card').style.display='flex';
      paused=true;
    }
    function maybeShowCard(){
      if (!game) return;
      for (var i=0;i<game.fires.length;i++){
        var cls=game.fires[i].cls;
        if (!seen[cls]){ seen[cls]=true; showCard(cls); return; }
      }
    }

    // ITEM-057 Version A: pre-game instruction overlay (phone-landscape only).
    // The instruction copy is reused verbatim from the inline #hint element, so the
    // German text stays in exactly one place. Shown once per level load, and ONLY
    // when the landscape-phone media query matches — so desktop NEVER shows it. It
    // is fully dismissible and never blocks the real "Einsatz starten" control.
    var pregameShown = false;
    function isPhoneLandscape(){
      try { return window.matchMedia("(orientation: landscape) and (max-height: 500px)").matches; }
      catch(e){ return false; }
    }
    function maybeShowPregame(){
      if (pregameShown || !isPhoneLandscape()) return;
      var pg=document.getElementById('pregame'); if (!pg) return;
      var hint=document.getElementById('hint'), body=document.getElementById('pregameText');
      if (body && hint) body.textContent = hint.textContent;   // reuse the exact copy
      pg.style.display='flex'; pregameShown=true;
      var ok=document.getElementById('pregameOk');
      if (ok){ try { ok.focus(); } catch(e){} }
    }
    function hidePregame(){
      var pg=document.getElementById('pregame'); if (pg) pg.style.display='none';
    }

    var prevStatus='idle';
    function frame(now){
      var dt = Math.min((now - last)/1000, 0.05); last = now;
      if (game && game.status==='playing' && !paused){
        advance(dt); maybeShowCard();
        // Anton whispers ONE light, safe tactical hint a moment into the operation.
        if (!hintShown && antonLines && antonLines.hint && game.elapsed > 2.5){
          showFeedback(antonLines.hint, 'ok');
          feedbackUntil = performance.now() + 6500;  // give the hint a little longer
          hintShown = true;
        }
      }
      if (performance.now() > feedbackUntil) document.getElementById('feedback').textContent='';
      render();
      if (game && game.status!==prevStatus){
        if (game.status==='won'){ playSound('win'); handleEnd(); }
        else if (game.status==='lost'){ playSound('lose'); handleEnd(); }
        updateControls();
        prevStatus = game.status;
      }
      requestAnimationFrame(frame);
    }

    function loadLevel(i){
      fetch('/api/level/'+i+apiLang()).then(function(r){return r.json();}).then(function(data){
        if (data.error) return;
        level = data; game = newGame(level); sprays = []; prevStatus='idle';
        seen = {}; paused = false; hintShown = false; currentIndex = i; keyIndex = -1;
        antonLines = data.anton || {};
        missionKey = data.key; missionNo = data.mission; isCampaign = !!data.campaign;
        document.getElementById('card').style.display = 'none';
        document.getElementById('recap').style.display = 'none';
        document.getElementById('feedback').textContent = '';
        canvas.width = data.size.w; canvas.height = data.size.h;
        document.getElementById('place').textContent = data.name + ' · ' + data.place_de;
        setLives(data.building.lives);
        updateControls(); updateBudget(); renderLevelBar(); updateAntonMood();
        // Anton opens the mission by sensing it and telling his anecdote.
        showMissionIntro();
        // ITEM-057 Version A: on phone-landscape, show the pre-game instruction
        // overlay once for this freshly-loaded level (desktop/portrait never see it).
        pregameShown = false; maybeShowPregame();
      }).catch(function(){ document.getElementById('place').textContent=tr('level_load_error'); });
    }

    // ITEM-036: each tool is a card with a two-tone flat extinguisher graphic + label
    // (name/slot + cost) + an "ℹ Info" affordance. Clicking the card selects the tool
    // for placement (the game action); ℹ opens the info pop-up. Tools stay tellable
    // apart by label + shape (not colour), keyboard-selectable (1..N) and touch-sized.
    function loadTools(){
      return fetch('/api/tools'+apiLang()).then(function(r){return r.json();}).then(function(list){
        toolsList=list; var bar=document.getElementById('toolPalette'); bar.innerHTML='';
        list.forEach(function(t, idx){
          toolMap[t.id]=t;
          var wrap=document.createElement('div'); wrap.className='tool';
          var btn=document.createElement('button'); btn.className='toolbtn';
          btn.setAttribute('data-tool', t.id); btn.setAttribute('data-cost', t.cost);
          btn.setAttribute('aria-label', t.name_de + ' — ' + t.cost);
          var cv=document.createElement('canvas'); cv.className='toolcv'; cv.width=34; cv.height=46; cv.setAttribute('data-tool', t.id);
          var nm=document.createElement('span'); nm.className='tname'; nm.textContent=(idx+1)+'. '+t.short;
          var cs=document.createElement('span'); cs.className='tcost'; cs.textContent='💰 '+t.cost;
          btn.appendChild(cv); btn.appendChild(nm); btn.appendChild(cs);
          btn.onclick=function(){ selectedTool=t.id; updateBudget(); };
          var info=document.createElement('button'); info.className='toolinfo'; info.textContent='ℹ Info';
          info.setAttribute('aria-label', 'Info: ' + t.name_de);
          info.onclick=function(){ openToolInfo(t.id); };
          wrap.appendChild(btn); wrap.appendChild(info); bar.appendChild(wrap);
        });
        paintToolCanvases();
      }).catch(function(){});
    }
    // Draw the little extinguisher graphic on each palette card (also redrawn when the
    // high-contrast theme changes, so the tool colour stays readable).
    function paintToolCanvases(){
      Array.prototype.forEach.call(document.querySelectorAll('#toolPalette canvas.toolcv'), function(cv){
        var t=toolMap[cv.getAttribute('data-tool')]; if (!t) return;
        var c=null; try { c=cv.getContext('2d'); } catch(e){ return; }
        if (!c) return;
        c.clearRect(0,0,cv.width,cv.height);
        drawExtShape(c, 8, 12, 18, 26, toolColour(t.hex));
      });
    }
    // Tool info pop-up (ITEM-036). Facts are DERIVED from the guarded fire-safety
    // matrix (same source as "Antons Wissen") — nothing is invented here.
    function openToolInfo(id){
      var t=toolMap[id]; if (!t) return;
      selectedTool=id; updateBudget();                 // selecting still selects for placement
      document.getElementById('tiTitle').textContent = t.name_de + ' (' + t.short + ')';
      var cv=document.getElementById('tiCanvas'), c=null;
      try { c=cv.getContext('2d'); } catch(e){ c=null; }
      if (c){ c.clearRect(0,0,cv.width,cv.height); drawExtShape(c, 18, 20, 26, 40, toolColour(t.hex)); }
      var goods=[], weaks=[], dangers=[];
      (window._classOrder||[]).forEach(function(cid){
        var o=matrixMap[cid+'|'+id], cc=classMap[cid]||{};
        var lab=(cc.icon||'')+' '+(cc.name_de||cid)+' ('+(cc.letter||'')+')';
        if (o==='good') goods.push(lab); else if (o==='danger') dangers.push(lab); else if (o==='weak') weaks.push(lab);
      });
      var html='<p style="color:var(--muted); margin:.2rem 0;">'+tr('ti_cost')+t.cost+'</p>';
      html+='<div style="color:var(--c); margin:.2rem 0;">'+tr('ti_correct')+(goods.join(', ')||'—')+'</div>';
      if (weaks.length) html+='<div style="color:var(--muted); margin:.2rem 0;">'+tr('ti_weak')+weaks.join(', ')+'</div>';
      if (dangers.length) html+='<div style="color:var(--red); margin:.2rem 0;">'+tr('ti_danger')+dangers.join(', ')+'</div>';
      document.getElementById('tiBody').innerHTML=html;
      if (game && game.status==='playing') paused=true;
      document.getElementById('toolInfo').style.display='flex';
    }
    function closeToolInfo(){ document.getElementById('toolInfo').style.display='none'; paused=false; last=performance.now(); }

    // Tap/click a build spot to place the selected tool there. The screen point is
    // scaled to board coordinates (works when the board is shrunk on a tablet). The
    // hit radius is finger-friendly (ITEM-020).
    function nearestSpot(clientX, clientY){
      if (!level) return -1;
      var rect=canvas.getBoundingClientRect();
      if (!rect.width || !rect.height) return -1;
      var x=(clientX-rect.left)*(canvas.width/rect.width);
      var y=(clientY-rect.top)*(canvas.height/rect.height);
      var spots=level.build_spots, bestI=-1, bestD=null;
      for (var i=0;i<spots.length;i++){
        var d=Math.hypot(spots[i][0]-x, spots[i][1]-y);
        if (d<=HIT_RADIUS && (bestD===null || d<bestD)){ bestD=d; bestI=i; }
      }
      return bestI;
    }
    function boardPlaceAt(clientX, clientY){
      if (!game || !selectedTool || !level) return;
      var i=nearestSpot(clientX, clientY);
      if (i>=0){ keyIndex=i; placeTower(i, selectedTool); }
    }
    // ITEM-042: tapping/clicking an already-occupied spot while NO tool is selected
    // removes the tower there. A distinct path from placement — boardPlaceAt (and
    // placeTower) above are untouched, so whenever a tool IS selected a tap can only
    // ever place, never remove; the one-tap-one-tower placement guarantee holds.
    function boardTapAt(clientX, clientY){
      if (!game || !level) return;
      if (selectedTool){ boardPlaceAt(clientX, clientY); return; }
      var i=nearestSpot(clientX, clientY);
      if (i>=0 && towerAt(i)){ keyIndex=i; removeTower(i); }
    }
    // ONE input path so a single tap can never place twice (touch + synthetic-click
    // double-fire is avoided): use Pointer Events where supported (covers mouse, touch
    // and pen); otherwise fall back to click + touchend, with touchend suppressing the
    // synthetic click. Desktop mouse behaves exactly as before.
    if (window.PointerEvent){
      canvas.addEventListener('pointerup', function(e){
        if (e.pointerType==='mouse' && e.button!==0) return;   // left mouse only
        boardTapAt(e.clientX, e.clientY);
      });
    } else {
      canvas.addEventListener('click', function(e){ boardTapAt(e.clientX, e.clientY); });
      canvas.addEventListener('touchend', function(e){
        if (e.changedTouches && e.changedTouches.length){
          e.preventDefault();                                  // stop the following synthetic click
          var t=e.changedTouches[0]; boardTapAt(t.clientX, t.clientY);
        }
      }, {passive:false});
    }

    // The level bar shows the four story missions in play order (locked until the
    // one before is won) plus the training level as a free-choice side level (ITEM-027).
    function renderLevelBar(){
      var bar=document.getElementById('levelBar'); if (!bar) return; bar.innerHTML='';
      var camp=levelsMeta.filter(function(l){ return l.campaign && l.mission; })
                         .slice().sort(function(a,b){ return a.mission-b.mission; });
      var side=levelsMeta.filter(function(l){ return !(l.campaign && l.mission); });
      camp.forEach(function(l){
        var unlocked=missionUnlocked(l.mission);
        var btn=document.createElement('button');
        btn.textContent='M'+l.mission+'. '+l.name + (unlocked ? '' : ' 🔒');
        btn.disabled=!unlocked;
        if (!unlocked) btn.title=tr('lvl_locked_title');
        if (l.index===currentIndex) btn.className='active';
        btn.onclick=function(){ if (missionUnlocked(l.mission)) loadLevel(l.index); };
        bar.appendChild(btn);
      });
      side.forEach(function(l){
        var btn=document.createElement('button');
        btn.textContent=tr('lvl_practice')+l.name;
        if (l.index===currentIndex) btn.className='active';
        btn.onclick=function(){ loadLevel(l.index); };
        bar.appendChild(btn);
      });
      // A small, unobtrusive "start over" control (clears saved campaign progress).
      var reset=document.createElement('button');
      reset.textContent=tr('lvl_reset');
      reset.title=tr('lvl_reset_title');
      reset.style.fontSize='.78rem'; reset.style.opacity='.65';
      reset.style.borderStyle='dashed'; reset.style.padding='.25rem .6rem';
      reset.onclick=resetProgress;
      bar.appendChild(reset);
    }
    function buildLevelBar(){
      fetch('/api/levels'+apiLang()).then(function(r){return r.json();}).then(function(list){
        levelsMeta=list; loadProgress(); renderLevelBar();
        var camp=levelsMeta.filter(function(l){ return l.campaign && l.mission; })
                           .slice().sort(function(a,b){ return a.mission-b.mission; });
        loadLevel(camp.length ? camp[0].index : 0);
      });
    }

    // --- German→English switch: language load, toggle UI, and live re-render -----
    // Persisted in localStorage 'fd_lang' with the same guarded pattern as
    // fd_contrast / fd_sound; a browser that blocks storage never throws.
    function saveLang(l){ try { window.localStorage.setItem('fd_lang', l==='en'?'en':'de'); } catch(e){} }
    function loadLang(){
      var l = null;
      try { var v = window.localStorage.getItem('fd_lang'); if (v==='en'||v==='de') l=v; } catch(e){ l=null; }
      if (!l){ try { l = (document.documentElement.lang==='en') ? 'en' : 'de'; } catch(e){ l='de'; } }
      lang = (l==='en') ? 'en' : 'de';
      try { document.documentElement.lang = lang; } catch(e){}
      updateLangToggle(); applyStaticI18n();
    }
    function updateLangToggle(){
      var seg=document.getElementById('langToggle'); if (!seg) return;
      Array.prototype.forEach.call(seg.querySelectorAll('.seg-btn'), function(b){
        var on = b.getAttribute('data-lang')===lang;
        b.classList.toggle('active', on);
        b.setAttribute('aria-pressed', on ? 'true':'false');
      });
    }
    // Re-fetch /api/levels in the new language and swap ONLY the names in-place, so
    // the mission-selector keeps the same indices/order + the current selection and
    // saved progress. Must run before renderLevelBar() in setLang (ITEM req 5b).
    function refreshLevelsMeta(){
      return fetch('/api/levels'+apiLang()).then(function(r){return r.json();}).then(function(list){
        if (Array.isArray(list) && levelsMeta.length===list.length){
          for (var i=0;i<list.length;i++){ levelsMeta[i].name = list[i].name; }
        } else if (Array.isArray(list)){
          levelsMeta = list;
        }
      }).catch(function(){});
    }
    // Re-fetch the CURRENT level in the new language and merge ONLY its TEXT fields
    // into the live `level` (which is also game.level) so geometry/schedule/progress
    // and any in-progress game are untouched (ITEM req 5a).
    function relocalizeLevel(){
      if (currentIndex<0) return Promise.resolve();
      return fetch('/api/level/'+currentIndex+apiLang()).then(function(r){return r.json();}).then(function(d){
        if (!d || d.error || !level) return;
        level.name = d.name; level.place_de = d.place_de;
        if (level.building && d.building) level.building.name_de = d.building.name_de;
        antonLines = d.anton || antonLines; level.anton = antonLines;
        if (d.vignette) level.vignette = d.vignette;
        try { document.getElementById('place').textContent = d.name + ' · ' + d.place_de; } catch(e){}
      }).catch(function(){});
    }
    // Switch language live — NO reload, and WITHOUT resetting an in-progress game or
    // campaign progress. Re-fetch every language-bearing feed and re-render.
    function setLang(l){
      lang = (l==='en') ? 'en' : 'de';
      saveLang(lang);
      try { document.documentElement.lang = lang; } catch(e){}
      updateLangToggle();
      applyStaticI18n();                 // static chrome labels
      // Re-fetch content feeds (classes/tools/matrix/anton) + levels meta + this
      // level's text, then re-render everything that shows language.
      Promise.all([loadClasses(), loadTools(), loadMatrix(), loadAnton(),
                   refreshLevelsMeta(), relocalizeLevel()]).then(function(){
        renderLevelBar();                // 5b: mission buttons re-localize, selection kept
        updateAntonMood();
        updateControls(); updateBudget();
        loadStatus();                    // 5c: footer/status line re-localizes
        // If a text overlay is open, re-render it in the new language.
        var libEl=document.getElementById('lib');
        if (libEl && libEl.style.display && libEl.style.display!=='none') buildLib();
        var recapEl=document.getElementById('recap');
        if (recapEl && recapEl.style.display && recapEl.style.display!=='none') showRecap();
      });
    }

    function loadClasses(){
      return fetch('/api/classes'+apiLang()).then(function(r){return r.json();}).then(function(list){
        var leg=document.getElementById('classLegend'); leg.innerHTML='';
        window._classOrder = list.map(function(c){ return c.id; });
        var CV={A:'--a',B:'--b',C:'--c',electrical:'--e',D:'--d',F:'--f'};
        list.forEach(function(c){
          classMap[c.id]=c;
          // Use the flat-palette CSS variable so the legend matches the canvas and
          // follows the high-contrast toggle automatically (visual only).
          var el=document.createElement('span'); el.style.color='var('+(CV[c.id]||'--ink')+')';
          el.textContent=c.icon+' '+c.name_de+' ('+c.letter+')'; leg.appendChild(el);
        });
      }).catch(function(){});
    }

    function loadMatrix(){
      return fetch('/api/matrix'+apiLang()).then(function(r){return r.json();}).then(function(list){
        matrixMap={}; reasonMap={};
        list.forEach(function(x){
          matrixMap[x['class'] + '|' + x.tool] = x.outcome;
          if (x.reason) reasonMap[x['class'] + '|' + x.tool] = x.reason;
        });
      }).catch(function(){});
    }

    function loadStatus(){
      fetch('/health').then(function(r){return r.json();}).then(function(h){
        document.getElementById('foot').textContent =
          tr('status_db') + (h.status==='ok'?tr('status_ready'):tr('status_missing')) + ' · ' + h.fire_classes + tr('status_classes') + h.tools + tr('status_tools');
      }).catch(function(){});
    }
    // Anton's growth-arc lines + finale (ITEM-028). A fetch failure degrades quietly.
    function loadAnton(){
      return fetch('/api/anton'+apiLang()).then(function(r){return r.json();}).then(function(d){
        antonArc = (d && d.courage) || []; antonFinale = (d && d.finale) || {};
        updateAntonMood();
      }).catch(function(){ antonArc=[]; antonFinale={}; });
    }

    document.getElementById('startBtn').onclick = onStartButton;
    document.getElementById('cardOk').onclick = function(){
      document.getElementById('card').style.display='none'; paused=false; last=performance.now();
    };
    // ITEM-057 Version A: pre-game overlay dismissal — button, backdrop tap, and Esc
    // (Esc is handled at the top of the keydown listener below). None of these touch
    // how a wave actually starts; the player still presses "Einsatz starten".
    (function(){
      var pg=document.getElementById('pregame'), ok=document.getElementById('pregameOk');
      if (ok) ok.onclick = function(){ hidePregame(); };
      if (pg) pg.addEventListener('click', function(e){ if (e.target===pg) hidePregame(); });
    })();
    document.getElementById('libBtn').onclick = openLib;
    document.getElementById('libClose').onclick = closeLib;
    document.getElementById('recapLib').onclick = openLib;
    document.getElementById('recapAgain').onclick = function(){
      document.getElementById('recap').style.display='none'; onStartButton();
    };
    document.getElementById('vigClose').onclick = closeVignette;
    document.getElementById('finClose').onclick = closeFinale;
    document.getElementById('tiClose').onclick = closeToolInfo;

    // --- Große Schrift / Hoher Kontrast (ITEM-020) — presentational only, persisted
    //     with the same guarded localStorage pattern (a storage failure never throws).
    function applyContrast(on){
      contrastEnabled=!!on;
      if (document.body){ if (on) document.body.classList.add('hc'); else document.body.classList.remove('hc'); }
      var cb=document.getElementById('contrastToggle'); if (cb) cb.checked=!!on;
      paintToolCanvases();   // tool colours are lightened for the dark field — repaint
    }
    function saveContrast(on){ try { window.localStorage.setItem('fd_contrast', on?'1':'0'); } catch(e){} }
    function loadContrast(){ var on=false; try { on = window.localStorage.getItem('fd_contrast')==='1'; } catch(e){ on=false; } applyContrast(on); }
    document.getElementById('contrastToggle').onchange = function(e){ applyContrast(e.target.checked); saveContrast(e.target.checked); };
    loadContrast();

    // --- Ton / mute toggle (ITEM-019) — same wiring/persistence shape as the toggles
    //     above. Muted => playSound returns immediately, so nothing is heard.
    var _soundCb = document.getElementById('soundToggle');
    if (_soundCb) _soundCb.onchange = function(e){ soundEnabled = e.target.checked; saveSound(e.target.checked); if (soundEnabled) initAudio(); };
    loadSound();

    // --- German→English switch (DE | EN segmented toggle) — same guarded-persistence
    //     shape as the toggles above. Clicking a half switches language live via
    //     setLang(): no reload, in-progress game and campaign progress preserved.
    (function(){
      var seg=document.getElementById('langToggle');
      if (!seg) return;
      Array.prototype.forEach.call(seg.querySelectorAll('.seg-btn'), function(b){
        b.onclick=function(){ setLang(b.getAttribute('data-lang')); };
      });
    })();
    loadLang();   // decide the language (localStorage 'fd_lang' or served <html lang>) before first fetch

    // --- ITEM-053 landscape-phone menus (Option B) — purely presentational: these
    //     handlers only toggle a "dd-open" class, which has no visual effect unless
    //     the landscape media query above is active, so they are harmless on desktop
    //     and portrait. Every element lookup is guarded, so a missing element (e.g.
    //     an older cached page) can never throw.
    (function(){
      var missionBtn = document.getElementById('missionMenuBtn');
      var gearBtn = document.getElementById('gearMenuBtn');
      var mLevelBar = document.getElementById('levelBar');
      var mSettings = document.getElementById('settingsGroup');
      function setOpen(el, btn, on){
        if (!el) return;
        el.classList.toggle('dd-open', !!on);
        if (btn) btn.setAttribute('aria-expanded', on ? 'true' : 'false');
      }
      function closeMenus(){ setOpen(mLevelBar, missionBtn, false); setOpen(mSettings, gearBtn, false); }
      if (missionBtn){
        missionBtn.onclick = function(e){
          if (e) e.stopPropagation();
          var willOpen = !(mLevelBar && mLevelBar.classList.contains('dd-open'));
          closeMenus(); setOpen(mLevelBar, missionBtn, willOpen);
        };
      }
      if (gearBtn){
        gearBtn.onclick = function(e){
          if (e) e.stopPropagation();
          var willOpen = !(mSettings && mSettings.classList.contains('dd-open'));
          closeMenus(); setOpen(mSettings, gearBtn, willOpen);
        };
      }
      if (mLevelBar){
        mLevelBar.addEventListener('click', function(e){
          if (e) e.stopPropagation();
          if (e && e.target && e.target.tagName === 'BUTTON') setOpen(mLevelBar, missionBtn, false);
        });
      }
      if (mSettings){
        mSettings.addEventListener('click', function(e){ if (e) e.stopPropagation(); });
      }
      document.addEventListener('click', closeMenus);
    })();

    // --- Spot-based keyboard control (ITEM-020): fully playable without a mouse.
    //     1..N pick an extinguisher; arrows move the build-spot highlight; Enter places;
    //     Space starts/restarts. Never hijacks a focused form control or button, and is
    //     inert while a modal/overlay is open, so it can't interfere with mouse/touch.
    function isFormFocus(){
      var el=document.activeElement; if (!el) return false;
      var tag=(el.tagName||'').toUpperCase();
      return tag==='INPUT'||tag==='TEXTAREA'||tag==='SELECT'||el.isContentEditable;
    }
    function isButtonFocus(){ var el=document.activeElement; return !!(el && (el.tagName||'').toUpperCase()==='BUTTON'); }
    function anyOverlayOpen(){
      var ids=['card','recap','lib','vignette','finale','toolInfo'];
      for (var i=0;i<ids.length;i++){ var el=document.getElementById(ids[i]);
        if (el && el.style.display && el.style.display!=='none') return true; }
      return false;
    }
    function moveHighlight(delta){
      if (!level || !level.build_spots.length) return;
      keyboardActive=true;
      if (keyIndex<0){ keyIndex=(delta>0?0:level.build_spots.length-1); }
      else { keyIndex=(keyIndex+delta+level.build_spots.length)%level.build_spots.length; }
    }
    function selectToolSlot(n){ if (!toolsList || n<1 || n>toolsList.length) return; selectedTool=toolsList[n-1].id; updateBudget(); }
    document.addEventListener('keydown', function(e){
      // ITEM-057 Version A: while the pre-game overlay is open it is modal — Esc
      // closes it, its focused "Los geht's" button still activates natively, and all
      // other game keys are swallowed so they can't act on the hidden board.
      var pg=document.getElementById('pregame');
      if (pg && pg.style.display && pg.style.display!=='none'){
        if (e.key==='Escape' || e.key==='Esc'){ hidePregame(); e.preventDefault(); }
        return;
      }
      if (anyOverlayOpen() || isFormFocus()) return;
      var k=e.key;
      if (k>='1' && k<='9'){ selectToolSlot(parseInt(k,10)); e.preventDefault(); return; }
      if (k==='ArrowRight'||k==='ArrowDown'){ moveHighlight(1); e.preventDefault(); return; }
      if (k==='ArrowLeft'||k==='ArrowUp'){ moveHighlight(-1); e.preventDefault(); return; }
      if (k==='Enter'){
        if (isButtonFocus()) return;               // let a focused button activate normally
        keyboardActive=true;
        if (game && selectedTool && keyIndex>=0) placeTower(keyIndex, selectedTool);
        e.preventDefault(); return;
      }
      // ITEM-042/ITEM-020: Delete/Backspace removes the tower at the keyboard-
      // highlighted build spot — the keyboard-parity path for the same removal
      // boardTapAt offers by touch/click.
      if (k==='Delete'||k==='Backspace'){
        if (isButtonFocus()) return;
        if (game && keyIndex>=0) removeTower(keyIndex);
        e.preventDefault(); return;
      }
      if (k===' '||k==='Spacebar'){
        if (isButtonFocus()) return;               // let a focused button activate normally
        onStartButton(); e.preventDefault(); return;
      }
    });
    // Load classes, tools, the fire-safety matrix, and Anton's arc first, then levels.
    Promise.all([loadClasses(), loadTools(), loadMatrix(), loadAnton()]).then(function(){ buildLevelBar(); });
    loadStatus();
    last = performance.now();
    requestAnimationFrame(frame);
  