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
    /// Persiste entre escenas (menú ↔ juego).
    /// </summary>
    public class AudioManager : MonoBehaviour
    {
        AudioSource[] music = new AudioSource[2];
        int musicActive;
        AudioSource ambience;
        readonly List<AudioSource> sfxPool = new List<AudioSource>();
        int sfxIndex;
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
            for (int i = 0; i < 24; i++)
            {
                var go = new GameObject("Sfx" + i);
                go.transform.SetParent(transform, false);
                var s = go.AddComponent<AudioSource>();
                s.playOnAwake = false; s.rolloffMode = AudioRolloffMode.Linear; s.minDistance = 4f; s.maxDistance = 45f; s.dopplerLevel = 0f;
                sfxPool.Add(s);
            }
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
            ambience.volume = Mathf.MoveTowards(ambience.volume, Settings.MasterVolume * Settings.SfxVolume * ambienceVol, Time.unscaledDeltaTime * 0.5f);
            // cámara lenta: el mundo suena más grave (el hit-stop de cada golpe no: el choque arrancaba grave)
            float scale = Game.Time != null ? Game.Time.SlowMoScale : 1f;
            float pitch = Game.IsPaused ? 1f : Mathf.Lerp(0.55f, 1f, Mathf.Clamp01(scale));
            foreach (var s in sfxPool) if (s.isPlaying) s.pitch = s.pitch / Mathf.Max(0.01f, lastPitchMul) * pitch;
            lastPitchMul = pitch;
            musicDuck = Mathf.MoveTowards(musicDuck, Game.IsPaused ? 0.45f : 1f, Time.unscaledDeltaTime * 2f);
        }
        float lastPitchMul = 1f;

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
            var s = sfxPool[sfxIndex];
            sfxIndex = (sfxIndex + 1) % sfxPool.Count;
            s.Stop();
            s.clip = clip;
            float pv = pitchVar >= 0f ? pitchVar : entry.pitchVariance;
            s.pitch = (1f + Random.Range(-pv, pv)) * lastPitchMul;
            s.volume = volume * entry.volume * Settings.MasterVolume * Settings.SfxVolume;
            if (pos.HasValue && entry.spatial)
            {
                s.transform.position = pos.Value;
                s.spatialBlend = 0.75f;
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
