using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Envoltorio del Animator controlado por código (sin "sopa de triggers"):
    /// cada acción hace CrossFade a un estado con su propio blend, y la velocidad se
    /// modula frame a frame (curvas de timing, hit-stop por personaje, cámara lenta).
    /// </summary>
    public class CharacterAnimator
    {
        public Animator Animator { get; private set; }
        // duración por ESTADO (la calcula Tools/Unity/generate_assets.py: los estados y sus
        // clips se llaman distinto, p. ej. Attack1 -> "Attackk1"); 'lengths' (por clip) queda de respaldo
        readonly Dictionary<string, float> stateLengths = new Dictionary<string, float>();
        readonly Dictionary<string, float> lengths = new Dictionary<string, float>();
        readonly Dictionary<string, int> hashes = new Dictionary<string, int>();
        static readonly int SpeedParam = Animator.StringToHash("Speed");
        bool hasSpeedParam;

        float freezeUntil;
        float speedMul = 1f;   // global: SetSpeed (curvas de timing, furia)
        float stateMul = 1f;   // del estado actual: Play(..., speed); vuelve a 1 en el próximo Play
        public string Current { get; private set; } = "";
        public float StateSpeed => speedMul * stateMul;

        public bool Valid => Animator != null && Animator.runtimeAnimatorController != null;

        public void Init(Animator a)
        {
            Animator = a;
            lengths.Clear();
            stateLengths.Clear();
            if (a == null) return;
            a.applyRootMotion = false;
            a.cullingMode = AnimatorCullingMode.CullUpdateTransforms;
            if (a.runtimeAnimatorController != null)
            {
                foreach (var clip in a.runtimeAnimatorController.animationClips)
                    if (clip != null && !lengths.ContainsKey(clip.name)) lengths[clip.name] = clip.length;
                foreach (var p in a.parameters)
                    if (p.nameHash == SpeedParam && p.type == AnimatorControllerParameterType.Float) hasSpeedParam = true;
                var entry = Game.LoadContent().CharacterByController(a.runtimeAnimatorController);
                if (entry != null && entry.stateNames != null && entry.stateLengths != null)
                    for (int i = 0; i < entry.stateNames.Length && i < entry.stateLengths.Length; i++)
                        if (!string.IsNullOrEmpty(entry.stateNames[i]) && entry.stateLengths[i] > 0.01f)
                            stateLengths[entry.stateNames[i]] = entry.stateLengths[i];
            }
        }

        int Hash(string state)
        {
            if (!hashes.TryGetValue(state, out int h)) { h = Animator.StringToHash(state); hashes[state] = h; }
            return h;
        }

        public bool HasState(string state)
        {
            return Valid && Animator.HasState(0, Hash(state));
        }

        /// <summary>Duración del clip del estado (segundos a velocidad 1). Usa 'fallback' si no se conoce.</summary>
        public float Length(string state, float fallback = 0.6f)
        {
            if (state == null) return fallback;
            if (stateLengths.TryGetValue(state, out float s) && s > 0.01f) return s;
            return lengths.TryGetValue(state, out float l) && l > 0.01f ? l : fallback;
        }

        /// <summary>
        /// CrossFade al estado. 'speed' es el multiplicador propio de este estado (se combina con
        /// SetSpeed y vuelve a 1 en el próximo Play que no lo indique).
        /// </summary>
        public void Play(string state, float fade = 0.08f, float normalizedOffset = 0f, float speed = 1f)
        {
            if (!Valid) return;
            int h = Hash(state);
            if (!Animator.HasState(0, h))
            {
                // Estado faltante: no rompemos el juego, solo avisamos una vez.
                if (warned.Add(state)) Debug.LogWarning($"[Nindo] El Animator de '{Animator.gameObject.name}' no tiene el estado '{state}'.");
                return;
            }
            Current = state;
            stateMul = speed;
            // el offset explícito (aunque sea 0) hace que repetir el estado actual (Hit→Hit, embestida→embestida)
            // lo reinicie con una auto-transición en vez de seguir desde donde estaba
            Animator.CrossFadeInFixedTime(h, fade, 0, normalizedOffset * Length(state));
        }

        static readonly HashSet<string> warned = new HashSet<string>();

        public void SetLocomotion(float normalizedSpeed, float dt)
        {
            if (!Valid || !hasSpeedParam) return;
            Animator.SetFloat(SpeedParam, normalizedSpeed, 0.08f, dt);
        }

        /// <summary>Multiplicador de velocidad global (curvas de timing, furia, etc.).</summary>
        public void SetSpeed(float mul) { speedMul = mul; }

        /// <summary>Congela solo a este personaje (hit-stop local, tiempo real).</summary>
        public void Freeze(float seconds)
        {
            freezeUntil = Mathf.Max(freezeUntil, Time.unscaledTime + seconds);
        }

        public bool Frozen => Time.unscaledTime < freezeUntil;

        /// <summary>
        /// Tiempo normalizado real del estado en el Animator (false si está en una transición o en otro
        /// estado): sirve para corregir la deriva entre el reloj del golpe y lo que se ve.
        /// </summary>
        public bool TryNormalizedTime(string state, out float n)
        {
            n = 0f;
            if (!Valid || Animator.IsInTransition(0)) return false;
            var info = Animator.GetCurrentAnimatorStateInfo(0);
            if (info.shortNameHash != Hash(state)) return false;
            n = info.normalizedTime;
            return true;
        }

        /// <summary>Llamar en Update.</summary>
        public void Tick()
        {
            if (!Valid) return;
            Animator.speed = Frozen ? 0f : speedMul * stateMul;
        }
    }
}
