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
        readonly Dictionary<string, float> lengths = new Dictionary<string, float>();
        readonly Dictionary<string, int> hashes = new Dictionary<string, int>();
        static readonly int SpeedParam = Animator.StringToHash("Speed");
        bool hasSpeedParam;

        float freezeUntil;
        float speedMul = 1f;
        public string Current { get; private set; } = "";
        public float StateSpeed { get; private set; } = 1f;

        public bool Valid => Animator != null && Animator.runtimeAnimatorController != null;

        public void Init(Animator a)
        {
            Animator = a;
            lengths.Clear();
            if (a == null) return;
            a.applyRootMotion = false;
            a.cullingMode = AnimatorCullingMode.CullUpdateTransforms;
            if (a.runtimeAnimatorController != null)
            {
                foreach (var clip in a.runtimeAnimatorController.animationClips)
                    if (clip != null && !lengths.ContainsKey(clip.name)) lengths[clip.name] = clip.length;
                foreach (var p in a.parameters)
                    if (p.nameHash == SpeedParam && p.type == AnimatorControllerParameterType.Float) hasSpeedParam = true;
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

        /// <summary>Duración del clip (segundos a velocidad 1). Usa 'fallback' si no se conoce.</summary>
        public float Length(string state, float fallback = 0.6f)
        {
            return lengths.TryGetValue(state, out float l) && l > 0.01f ? l : fallback;
        }

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
            StateSpeed = speed;
            Animator.CrossFadeInFixedTime(h, fade, 0, normalizedOffset * Length(state));
        }

        static readonly HashSet<string> warned = new HashSet<string>();

        public void SetLocomotion(float normalizedSpeed, float dt)
        {
            if (!Valid || !hasSpeedParam) return;
            Animator.SetFloat(SpeedParam, normalizedSpeed, 0.08f, dt);
        }

        /// <summary>Multiplicador de velocidad (curvas de timing, furia, etc.).</summary>
        public void SetSpeed(float mul) { speedMul = mul; StateSpeed = mul; }

        /// <summary>Congela solo a este personaje (hit-stop local, tiempo real).</summary>
        public void Freeze(float seconds)
        {
            freezeUntil = Mathf.Max(freezeUntil, Time.unscaledTime + seconds);
        }

        public bool Frozen => Time.unscaledTime < freezeUntil;

        /// <summary>Llamar en Update.</summary>
        public void Tick()
        {
            if (!Valid) return;
            Animator.speed = Frozen ? 0f : speedMul;
        }
    }
}
