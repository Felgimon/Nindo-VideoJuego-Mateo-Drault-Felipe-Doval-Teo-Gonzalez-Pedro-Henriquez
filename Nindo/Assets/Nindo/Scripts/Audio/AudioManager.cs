using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Nindo
{
    /// <summary>
    /// Audio de Nindo (reemplaza al SoundManager anterior): música con crossfade según zona /
    /// combate / jefe, ambiente en loop (grillos, viento, agua), efectos con variación de pitch
    /// desde un pool de AudioSources (2D y 3D), y pitch que baja en cámara lenta.
    /// Mezcla por niveles (ver Tier): los avisos de golpe y el parry son información, no adorno: no se
    /// les cambia el pitch, casi no se atenúan con la distancia y no se cortan por falta de voces.
    /// El oído está sobre Kaito (CameraDirector mueve el AudioListener), no en la cámara a 24 m.
    /// Persiste entre escenas (menú ↔ juego).
    /// </summary>
    public class AudioManager : MonoBehaviour
    {
        AudioSource[] music = new AudioSource[2];
        int musicActive;
        AudioSource ambience;
        readonly List<AudioSource> sfxPool = new List<AudioSource>();
        // estado de cada voz del pool: nivel, pitch propio (sin la cámara lenta), volumen, cuándo arrancó y hasta
        // cuándo puede sonar (algunas colas largas se cortan con fundido, ver MaxLength)
        Voice[] voices;
        struct Voice { public Tier tier; public bool noPitch; public float basePitch, baseVolume, start, maxLength; }
        string currentMusic = "";
        string currentAmbience = "";
        string exploreMusic = "explore";
        Coroutine fade;
        float musicDuck = 1f;
        readonly Dictionary<string, float> lastPlayed = new Dictionary<string, float>();

        /// <summary>
        /// Latencia de salida del audio (s reales): lo que tarda un Play() en sonar por los buffers del DSP
        /// (tamaño x cantidad / frecuencia; ~21 ms con el buffer de 256 de ProjectSettings, ~85 ms con 1024).
        /// </summary>
        public static float OutputLatency { get; private set; }

        /// <summary>
        /// ¿Ya hay que darle Play a un aviso que se tiene que OÍR 'lead' segundos (de juego) antes de algo que llega en
        /// 'eta'? Suma la latencia de salida y medio frame (el chequeo cae en el primer frame que cruza el umbral: en
        /// promedio medio frame tarde). Sin esto el hyōshigi se oía 50-90 ms tarde y reaccionarle caía fuera del parry.
        /// </summary>
        public static bool CueDue(float eta, float lead) => eta <= lead + OutputLatency * Time.timeScale + 0.5f * Time.deltaTime;

        static void MeasureLatency(bool deviceChanged = false)
        {
            AudioSettings.GetDSPBufferSize(out int len, out int num);
            OutputLatency = len * num / (float)Mathf.Max(1, AudioSettings.outputSampleRate);
        }

        public static AudioManager Ensure()
        {
            if (Game.Audio != null) return Game.Audio;
            var go = new GameObject("[Audio]");
            DontDestroyOnLoad(go);
            return go.AddComponent<AudioManager>();
        }

        void Awake()
        {
            if (Game.Audio != null && Game.Audio != this) { Destroy(gameObject); return; }
            Game.Audio = this;
            for (int i = 0; i < 2; i++)
            {
                music[i] = gameObject.AddComponent<AudioSource>();
                music[i].loop = true; music[i].playOnAwake = false; music[i].spatialBlend = 0f; music[i].volume = 0f;
                music[i].priority = 0;
            }
            ambience = gameObject.AddComponent<AudioSource>();
            ambience.loop = true; ambience.playOnAwake = false; ambience.spatialBlend = 0f; ambience.volume = 0f;
            // con el oído sobre Kaito: a menos de 6 m suena entero (la pelea entera), se apaga del todo a 35 m.
            // Con el oído en la cámara (24-31 m) todo sonaba al 50-60 % y saltaba +60 % en los planos cercanos
            for (int i = 0; i < VoiceCount; i++)
            {
                var go = new GameObject("Sfx" + i);
                go.transform.SetParent(transform, false);
                var s = go.AddComponent<AudioSource>();
                s.playOnAwake = false; s.rolloffMode = AudioRolloffMode.Linear; s.minDistance = 6f; s.maxDistance = 35f; s.dopplerLevel = 0f;
                sfxPool.Add(s);
            }
            voices = new Voice[VoiceCount];
            GameEvents.CombatStateChanged += OnCombat;
            SceneManager.sceneLoaded += OnSceneLoaded;
            // cambiar de dispositivo (auriculares, HDMI) cambia la frecuencia y los buffers
            MeasureLatency();
            AudioSettings.OnAudioConfigurationChanged += MeasureLatency;
        }

        void OnDestroy()
        {
            GameEvents.CombatStateChanged -= OnCombat;
            SceneManager.sceneLoaded -= OnSceneLoaded;
            AudioSettings.OnAudioConfigurationChanged -= MeasureLatency;
            if (Game.Audio == this) Game.Audio = null;
        }

        void OnSceneLoaded(Scene s, LoadSceneMode m)
        {
            // re-suscribir: GameEvents.Clear() se llama al recargar el dominio
            GameEvents.CombatStateChanged -= OnCombat;
            GameEvents.CombatStateChanged += OnCombat;
        }

        void OnCombat(bool inCombat)
        {
            if (Game.Combat != null && Game.Combat.ActiveBoss != null) return;
            // con Kaito muerto (o mientras suena un remate sin loop como "gameover") no se cambia la
            // música: al morir el combate "termina" y cortaba el jingle; StoryDirector.DeathRoutine
            // llama a ResumeExplore al reaparecer
            if (Game.Player != null && !Game.Player.IsAlive) return;
            if (StingerPlaying) return;
            PlayMusic(inCombat ? "combat" : exploreMusic, inCombat ? 1.2f : 3f);
        }

        /// <summary>¿Está sonando un tema sin loop (p. ej. "gameover")?</summary>
        bool StingerPlaying => !music[musicActive].loop && music[musicActive].isPlaying;

        /// <summary>La zona define qué música de exploración suena.</summary>
        public void SetExploreMusic(string key, string ambienceKey)
        {
            exploreMusic = string.IsNullOrEmpty(key) ? "explore" : key;
            if (Game.Combat == null || !Game.Combat.InCombat) PlayMusic(exploreMusic, 3f);
            if (!string.IsNullOrEmpty(ambienceKey)) PlayAmbience(ambienceKey);
        }

        // ------------------------------------------------------------------ música
        public void PlayMusic(string key, float fadeTime = 2f, bool loop = true)
        {
            if (key == currentMusic) return;
            var entry = FindMusic(key);
            if (entry == null) return;
            currentMusic = key;
            var clip = entry.clips[Random.Range(0, entry.clips.Length)];
            int next = 1 - musicActive;
            music[next].clip = clip;
            music[next].loop = loop;
            music[next].time = 0f;
            music[next].Play();
            if (fade != null) StopCoroutine(fade);
            fade = StartCoroutine(Crossfade(musicActive, next, fadeTime, entry.volume));
            musicActive = next;
        }

        /// <summary>Busca el tema; si falta usa uno parecido (explore_lago → explore, boss_final → boss...).</summary>
        NindoContent.AudioEntry FindMusic(string key)
        {
            var c = Game.LoadContent();
            string[] chain =
                key == "boss_final" ? new[] { key, "boss", "combat" } :
                key == "boss" ? new[] { key, "combat" } :
                key == "combat" ? new[] { key, "explore" } :
                key.StartsWith("explore_") ? new[] { key, "explore" } : new[] { key };
            foreach (var k in chain)
            {
                var e = c != null ? c.Music(k) : null;
                if (e != null && e.clips != null && e.clips.Length > 0) return e;
            }
            return null;
        }

        /// <summary>Vuelve a la música de la zona actual (después de morir o de una cinemática).</summary>
        public void ResumeExplore(float fadeTime = 2f)
        {
            currentMusic = "";
            PlayMusic(exploreMusic, fadeTime);
        }

        public void StopMusic(float fadeTime = 2f)
        {
            currentMusic = "";
            if (fade != null) StopCoroutine(fade);
            fade = StartCoroutine(Crossfade(musicActive, -1, fadeTime, 0f));
        }

        IEnumerator Crossfade(int from, int to, float time, float targetVol)
        {
            float t = 0f;
            float fromStart = music[from].volume;
            while (t < time)
            {
                t += Time.unscaledDeltaTime;
                float k = Mathf.Clamp01(t / time);
                music[from].volume = Mathf.Lerp(fromStart, 0f, k);
                if (to >= 0) { music[to].volume = Mathf.Lerp(0f, MusicVolume * targetVol, k); musicTargets[to] = targetVol; }
                yield return null;
            }
            music[from].Stop();
            fade = null;
        }

        readonly float[] musicTargets = { 1f, 1f };
        float MusicVolume => Settings.MasterVolume * Settings.MusicVolume * musicDuck;

        public void PlayAmbience(string key)
        {
            if (key == currentAmbience) return;
            var entry = Game.LoadContent().Ambience(key);
            if (entry == null || entry.clips == null || entry.clips.Length == 0) return;
            currentAmbience = key;
            ambience.clip = entry.clips[0];
            ambience.Play();
            ambienceVol = entry.volume;
        }
        float ambienceVol = 0.5f;

        void Update()
        {
            if (fade == null)
            {
                var src = music[musicActive];
                if (src.isPlaying) src.volume = Mathf.MoveTowards(src.volume, MusicVolume * musicTargets[musicActive], Time.unscaledDeltaTime);
            }
            // en combate el ambiente (agua, viento, cascada) baja ~4 dB: los avisos de golpe tienen que cortar
            bool fighting = Game.Combat != null && Game.Combat.InCombat;
            float ambTarget = Settings.MasterVolume * Settings.SfxVolume * ambienceVol * (fighting ? CombatAmbienceDuck : 1f);
            ambience.volume = Mathf.MoveTowards(ambience.volume, ambTarget, Time.unscaledDeltaTime * 0.5f);
            // cámara lenta: el mundo suena más grave. Solo la cámara lenta (el hit-stop de cada golpe no: el choque
            // arrancaba grave) y solo lo que no informa: avisos, parry y golpes conservan su altura (ver NoPitch)
            float scale = Game.Time != null ? Game.Time.SlowMoScale : 1f;
            slowPitch = Game.IsPaused ? 1f : Mathf.Lerp(0.55f, 1f, Mathf.Clamp01(scale));
            float now = Time.unscaledTime;
            for (int i = 0; i < sfxPool.Count; i++)
            {
                var s = sfxPool[i];
                if (!s.isPlaying) continue;
                ref var v = ref voices[i];
                s.pitch = v.noPitch ? v.basePitch : v.basePitch * slowPitch;
                if (v.maxLength <= 0f) continue;
                float left = v.maxLength - (now - v.start);
                if (left <= 0f) s.Stop();
                else s.volume = v.baseVolume * Mathf.Clamp01(left / TailFade);
            }
            musicDuck = Mathf.MoveTowards(musicDuck, Game.IsPaused ? 0.45f : 1f, Time.unscaledDeltaTime * 2f);
        }
        float slowPitch = 1f;

        // ------------------------------------------------------------------ mezcla
        const int VoiceCount = 24;
        const float CombatAmbienceDuck = 0.6f;
        const float TailFade = 0.35f;

        /// <summary>
        /// Niveles de la mezcla, del más importante al menos. Ordenan quién se queda con una voz cuando el pool está
        /// lleno (AudioSource.priority y el robo de voces) y quién respeta el pitch de la cámara lenta.
        /// Cue: lo que dice CUÁNDO apretar o qué pasó con el parry. Impact: golpes dados y recibidos.
        /// Body: cortes, dash, habilidades. Ambient: pasos, interfaz, diálogo.
        /// </summary>
        public enum Tier { Cue = 0, Impact = 1, Body = 2, Ambient = 3 }

        public static Tier TierOf(string key)
        {
            if (key.StartsWith("tell_") || key.StartsWith("parry") || key.Contains("_glint") || key == "clang" || key == "danger" || key == "posture_break")
                return Tier.Cue;
            if (key.StartsWith("hit") || key == "hurt" || key == "kill" || key == "death" || key.StartsWith("finisher") || key == "slam" || key == "boss_roar" || key == "perfect_dodge")
                return Tier.Impact;
            // el ambiente del mundo (cascada, braseros) nunca le saca una voz a un golpe o a un aviso
            if (key.StartsWith("step") || key.StartsWith("ui_") || key == "dialogue" || key == "lock" || key == "denied" ||
                key.StartsWith("falls_") || key.StartsWith("brazier"))
                return Tier.Ambient;
            return Tier.Body;
        }

        /// <summary>
        /// Sin pitch de cámara lenta: el parry y el choque son la recompensa (graves a 0.55-0.69 sonaban a error) y los
        /// avisos se reconocen por su altura (el hyōshigi, las notas de los avisos de un jefe). Los golpes dados y
        /// recibidos tampoco: son la confirmación de que conectó.
        /// </summary>
        public static bool NoPitch(string key) => TierOf(key) == Tier.Cue || key == "hit" || key == "hit_heavy" || key == "hurt";

        /// <summary>
        /// Mezcla 2D/3D: los avisos casi no se atenúan con la distancia (un atacante a 12 m tiene que oírse igual de
        /// claro) pero conservan la dirección; el resto es 3D alrededor de Kaito.
        /// </summary>
        static float SpatialBlend(Tier t) => t == Tier.Cue ? 0.4f : 0.75f;

        static int Priority(Tier t) => t == Tier.Cue ? 16 : t == Tier.Impact ? 64 : t == Tier.Body ? 128 : 200;

        /// <summary>Colas largas que tapan lo siguiente: el parry perfecto (4.6 s de reverb) se funde a los 2.2 s.</summary>
        static float MaxLength(string key) => key == "parry_perfect" ? 2.2f : 0f;

        /// <summary>
        /// Voz para un efecto nuevo: una libre; si no hay, la del nivel menos importante que lleve más tiempo sonando
        /// (antes se pisaba en ronda: una ráfaga de pasos podía cortar el parry perfecto o el aviso de un golpe).
        /// Nunca se roba una de nivel más importante que el que pide: en ese caso el efecto nuevo no suena.
        /// </summary>
        int PickVoice(Tier tier)
        {
            int best = -1;
            for (int i = 0; i < sfxPool.Count; i++)
            {
                if (!sfxPool[i].isPlaying) return i;
                if (voices[i].tier < tier) continue;
                if (best < 0 || voices[i].tier > voices[best].tier || (voices[i].tier == voices[best].tier && voices[i].start < voices[best].start)) best = i;
            }
            return best;
        }

        // ------------------------------------------------------------------ efectos
        /// <summary>Reproduce un efecto por clave (ver NindoContent.sfx). pos null = 2D.</summary>
        public void Play(string key, Vector3? pos = null, float volume = 1f, float pitchVar = -1f)
        {
            var entry = Game.LoadContent().Sfx(key);
            if (entry == null || entry.clips == null || entry.clips.Length == 0) return;
            // anti-spam: la misma clave no más de una vez cada 40 ms
            if (lastPlayed.TryGetValue(key, out float last) && Time.unscaledTime - last < 0.04f) return;
            lastPlayed[key] = Time.unscaledTime;
            var clip = entry.clips[Random.Range(0, entry.clips.Length)];
            if (clip == null) return;
            var tier = TierOf(key);
            int vi = PickVoice(tier);
            if (vi < 0) return;
            var s = sfxPool[vi];
            s.Stop();
            s.clip = clip;
            float pv = pitchVar >= 0f ? pitchVar : entry.pitchVariance;
            ref var v = ref voices[vi];
            v.tier = tier;
            v.noPitch = NoPitch(key);
            v.basePitch = 1f + Random.Range(-pv, pv);
            v.baseVolume = volume * entry.volume * Settings.MasterVolume * Settings.SfxVolume;
            v.start = Time.unscaledTime;
            v.maxLength = MaxLength(key);
            s.pitch = v.noPitch ? v.basePitch : v.basePitch * slowPitch;
            s.volume = v.baseVolume;
            s.priority = Priority(tier);
            if (pos.HasValue && entry.spatial)
            {
                s.transform.position = pos.Value;
                s.spatialBlend = SpatialBlend(tier);
            }
            else
            {
                s.transform.localPosition = Vector3.zero;
                s.spatialBlend = 0f;
            }
            s.Play();
        }
    }
}
