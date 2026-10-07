using UnityEngine;

namespace Nindo
{
    /// <summary>Personaje no jugable simple (el abuelo): se para, mira y camina en línea recta.</summary>
    public class NPC : MonoBehaviour
    {
        public string characterId = "grandpa";
        CharacterAnimator anim = new CharacterAnimator();
        Vector3 walkTarget;
        float walkSpeed;
        bool walking;

        public static NPC Spawn(string characterId, Vector3 pos, Quaternion rot, Transform parent)
        {
            // capa Ignore Raycast: el rayo de suelo (máscara Default), el de los enemigos y el NavMesh
            // en runtime no tienen que ver la cápsula (si no, el NPC "pisa" su propia cabeza y sale volando)
            var go = new GameObject("NPC_" + characterId) { layer = 2 };
            go.transform.SetParent(parent, false);
            go.transform.SetPositionAndRotation(pos, rot);
            var a = CharacterFactory.BuildModel(characterId, go.transform);
            // el FBX del abuelo trae también al ninja del secuestro ("Cube"): solo se ve en la escena del secuestro
            if (characterId == "grandpa")
                foreach (var r in go.GetComponentsInChildren<Renderer>(true)) if (r.name.StartsWith("Cube")) r.enabled = false;
            var npc = go.AddComponent<NPC>();
            npc.characterId = characterId;
            npc.anim.Init(a);
            npc.anim.Play("Locomotion", 0f);
            var col = go.AddComponent<CapsuleCollider>();
            col.radius = 0.35f; col.height = 1.5f; col.center = new Vector3(0, 0.75f, 0);
            return npc;
        }

        public void Play(string state, float fade = 0.15f) { anim.Play(state, fade); then = null; }

        /// <summary>Un clip que no es loop y, cuando termina, 'next' (los controllers no tienen transiciones: sin esto el
        /// abuelo quedaba congelado en el último cuadro de Freed como una estatua).</summary>
        public void PlayThen(string state, string next, float fade = 0.15f) { anim.Play(state, fade); thenFrom = state; then = next; }
        string then, thenFrom;

        /// <summary>Se da vuelta hacia un punto en 'seconds' (FaceTo gira de golpe: en cámara se veía saltar 180°).</summary>
        public void TurnTo(Vector3 p, float seconds)
        {
            Vector3 d = (p - transform.position).Flat();
            if (d.sqrMagnitude < 0.01f) return;
            turnFrom = transform.rotation; turnTo = Quaternion.LookRotation(d);
            turnT = 0f; turnDur = Mathf.Max(0.01f, seconds);
        }
        Quaternion turnFrom, turnTo;
        float turnT = 1f, turnDur = 1f;

        /// <summary>Salta al último frame del clip actual (p. ej. el ninja ya arrastrando al abuelo).</summary>
        public void SkipToEnd() { if (anim.Valid) anim.Play(anim.Current, 0f, 0.98f); }

        /// <summary>Se desliza hacia un punto sin girar ni cambiar la animación (arrastre).</summary>
        public void SlideTo(Vector3 target, float speed) { walkTarget = target; walkSpeed = speed; walking = true; sliding = true; }
        bool sliding;

        public void FaceTo(Vector3 p)
        {
            Vector3 d = (p - transform.position).Flat();
            if (d.sqrMagnitude > 0.01f) transform.rotation = Quaternion.LookRotation(d);
            turnT = 1f;   // manda sobre un TurnTo a medias
        }

        public void WalkTo(Vector3 target, float speed)
        {
            walkTarget = target; walkSpeed = speed; walking = true; sliding = false;
        }

        void Update()
        {
            float dt = Time.deltaTime;
            if (walking)
            {
                Vector3 d = (walkTarget - transform.position).Flat();
                if (d.magnitude < 0.2f) walking = false;
                else
                {
                    Vector3 step = d.normalized * Mathf.Min(walkSpeed * dt, d.magnitude);
                    Vector3 p = transform.position + step;
                    if (Physics.Raycast(p + Vector3.up * 2f, Vector3.down, out var hit, 6f, LayerMask.GetMask("Default"), QueryTriggerInteraction.Ignore)) p.y = hit.point.y;
                    transform.position = p;
                    if (!sliding) transform.rotation = CombatMath.Damp(transform.rotation, Quaternion.LookRotation(d), 8f, dt);
                }
            }
            if (turnT < 1f)
            {
                turnT = Mathf.Min(1f, turnT + dt / turnDur);
                transform.rotation = Quaternion.Slerp(turnFrom, turnTo, Mathf.SmoothStep(0f, 1f, turnT));
            }
            if (then != null && anim.Current == thenFrom && anim.TryNormalizedTime(thenFrom, out float shown) && shown >= 0.98f)
            {
                anim.Play(then, 0.25f);
                then = null;
            }
            if (!sliding) anim.SetLocomotion(walking ? 0.5f : 0f, dt);
            anim.Tick();
        }
    }
}
