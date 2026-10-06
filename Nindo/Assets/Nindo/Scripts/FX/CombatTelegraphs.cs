using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Avisos de ataque en el suelo (ensō). El jugador tiene que saber CUÁNDO pega cada enemigo para hacer
    /// parry, y desde la cámara alta la anticipación de la animación no alcanza. Por cada golpe se dibuja
    /// (shader Nindo/Telegraph) una pincelada que rodea al atacante y se cierra justo cuando hay que apretar:
    ///  * dorada: parry al cerrarse (el anillo se cierra 0.08 s antes del golpe, dentro de la ventana perfecta);
    ///  * roja y dentada, con la zona real que golpea: imparable, dash al cerrarse (centra los i-frames);
    ///  * a los pies de Kaito, para las olas que vienen hacia él.
    /// Lo maneja el enemigo (FXManager.BeginTell / EndTell): el progreso sale de su línea de tiempo, así que
    /// nunca miente. Barato: 1-2 quads por golpe, un raycast y un MaterialPropertyBlock por frame.
    /// </summary>
    public class CombatTelegraphs : MonoBehaviour
    {
        class Tell
        {
            public Enemy e;               // null = ola hacia Kaito
            public Transform ring, area;
            public MeshRenderer ringR, areaR;
            public float yaw, radius, seed, progress, closedFor, outT;
            public bool danger, visible, hasArea, areaLane;
            public TellOutcome? outcome;
            public Vector3 center, normal = Vector3.up;
            public TellArea areaShape;
        }

        [Tooltip("Ancho del trazo (m) antes del mínimo en píxeles")] public float strokeWidth = 0.14f;
        [Tooltip("Ancho mínimo del trazo en píxeles de pantalla")] public float minPixels = 12f;
        [Tooltip("Desde cuántos segundos antes del golpe se avisa una ola hacia Kaito")] public float projectileLead = 0.7f;

        readonly List<Tell> pool = new List<Tell>();
        readonly List<Tell> active = new List<Tell>();
        readonly Dictionary<Enemy, Tell> drawing = new Dictionary<Enemy, Tell>();
        Tell waveTell;
        float lastParry = -9f;
        Mesh quad;
        Material mat;
        MaterialPropertyBlock mpb;

        static readonly int IdColor = Shader.PropertyToID("_Color"), IdHotColor = Shader.PropertyToID("_HotColor"), IdInk = Shader.PropertyToID("_Ink"),
            IdMode = Shader.PropertyToID("_Mode"), IdProgress = Shader.PropertyToID("_Progress"), IdHot = Shader.PropertyToID("_Hot"),
            IdFlash = Shader.PropertyToID("_Flash"), IdDanger = Shader.PropertyToID("_Danger"), IdAlpha = Shader.PropertyToID("_Alpha"),
            IdRadius = Shader.PropertyToID("_Radius"), IdWidth = Shader.PropertyToID("_Width"), IdDot = Shader.PropertyToID("_Dot"),
            IdMinPx = Shader.PropertyToID("_MinPx"), IdOutcome = Shader.PropertyToID("_Outcome"), IdOutT = Shader.PropertyToID("_OutT"),
            IdSeed = Shader.PropertyToID("_Seed");

        const float FlashTime = 0.08f;
        static readonly Color DangerHot = new Color(1f, 0.62f, 0.5f);

        void Awake()
        {
            var sh = Resources.Load<Shader>("Shaders/NindoTelegraph");
            if (sh == null || !sh.isSupported) { enabled = false; return; }
            mat = new Material(sh) { name = "Telegraph" };
            mpb = new MaterialPropertyBlock();
            quad = new Mesh { name = "TelegraphQuad" };
            quad.vertices = new[] { new Vector3(-0.5f, 0, -0.5f), new Vector3(0.5f, 0, -0.5f), new Vector3(-0.5f, 0, 0.5f), new Vector3(0.5f, 0, 0.5f) };
            quad.uv = new[] { new Vector2(0, 0), new Vector2(1, 0), new Vector2(0, 1), new Vector2(1, 1) };
            quad.triangles = new[] { 0, 2, 1, 2, 3, 1 };
            quad.RecalculateBounds();
        }

        void OnEnable() => GameEvents.Parry += OnParry;
        void OnDisable() => GameEvents.Parry -= OnParry;
        void OnParry(bool perfect) => lastParry = Time.unscaledTime;

        void OnDestroy()
        {
            if (mat != null) Destroy(mat);
            if (quad != null) Destroy(quad);
        }

        // ------------------------------------------------------------------ API (la llama el enemigo)
        public void Begin(Enemy e)
        {
            if (e == null) return;
            if (drawing.TryGetValue(e, out var old)) Finish(old, TellOutcome.Cancelled);
            var t = Acquire();
            t.e = e;
            t.danger = e.StepKind == AttackKind.Unblockable;
            t.radius = e.Radius + (e is Boss ? 0.7f : 0.55f);
            t.seed = Random.value * 10f;
            drawing[e] = t;
        }

        public void End(Enemy e, TellOutcome outcome)
        {
            if (e != null && drawing.TryGetValue(e, out var t)) Finish(t, outcome);
        }

        void Finish(Tell t, TellOutcome outcome)
        {
            if (t.e != null) drawing.Remove(t.e);
            if (!t.visible) { Release(t); return; }   // nunca llegó a verse (cortado en la anticipación)
            t.outcome = outcome;
            t.outT = 0f;
            if (outcome == TellOutcome.Struck) t.progress = Mathf.Max(t.progress, 1f);
        }

        // ------------------------------------------------------------------ por frame
        void LateUpdate()
        {
            float dt = Time.deltaTime;
            UpdateWaveTell();
            for (int i = active.Count - 1; i >= 0; i--)
            {
                var t = active[i];
                if (t.outcome == null && t.e != null)
                {
                    var e = t.e;
                    if (!e.IsAlive || !e.gameObject.activeInHierarchy)
                    {
                        // se fue sin avisar (desactivado, destruido): se borra como golpe cortado
                        Finish(t, TellOutcome.Cancelled);
                        if (t.outcome == null) continue;   // nunca se vio: ya volvió al pool
                    }
                    else if (!e.InTell) continue;          // todavía en la anticipación temprana: no se dibuja
                    else
                    {
                        if (!t.visible)
                        {
                            // el trazo arranca del lado de Kaito y gira en sentido horario
                            var p = Game.Player;
                            Vector3 to = p != null ? (p.transform.position - e.transform.position).Flat() : e.transform.forward;
                            t.yaw = to.sqrMagnitude > 0.01f ? Mathf.Atan2(to.x, to.z) * Mathf.Rad2Deg : e.transform.eulerAngles.y;
                        }
                        t.progress = e.TellProgress01;
                        t.hasArea = e.TryGetTellArea(out t.areaShape);
                        t.center = e.transform.position;
                    }
                }
                if (t.outcome != null)
                {
                    t.outT += dt / OutcomeTime(t.outcome.Value);
                    if (t.outT >= 1f) { Release(t); continue; }
                }
                if (t.progress >= 1f) t.closedFor += dt; else t.closedFor = 0f;
                Show(t, true);
                Draw(t);
            }
        }

        static float OutcomeTime(TellOutcome o) => o == TellOutcome.Parried ? 0.22f : o == TellOutcome.Cancelled ? 0.14f : 0.15f;

        /// <summary>Ola de Mizuchi en camino: anillo dorado chico a los pies de Kaito, cerrándose al ritmo de la ola.</summary>
        void UpdateWaveTell()
        {
            var p = Game.Player;
            float eta = float.PositiveInfinity;
            Vector3 from = Vector3.zero;
            var cd = Game.Combat;
            if (cd != null && p != null && p.IsAlive && !Game.InCutscene)
            {
                var boss = cd.ActiveBoss;
                if (boss != null && boss.ProjectileEta < eta) { eta = boss.ProjectileEta; from = boss.ProjectileFrom; }
                var list = cd.Engaged;
                for (int i = 0; i < list.Count; i++)
                    if (list[i] != null && list[i].ProjectileEta < eta) { eta = list[i].ProjectileEta; from = list[i].ProjectileFrom; }
            }
            bool coming = eta <= projectileLead;
            if (waveTell != null && waveTell.outcome == null && !coming)
            {
                // la ola llegó (o se desvió hace un instante) o dejó de venir
                Finish(waveTell, Time.unscaledTime - lastParry < 0.2f ? TellOutcome.Parried : TellOutcome.Struck);
                waveTell = null;
            }
            if (!coming) return;
            if (waveTell == null || waveTell.outcome != null)
            {
                waveTell = Acquire();
                waveTell.radius = 0.8f;
                waveTell.seed = Random.value * 10f;
                Vector3 to = (from - p.transform.position).Flat();
                waveTell.yaw = to.sqrMagnitude > 0.01f ? Mathf.Atan2(to.x, to.z) * Mathf.Rad2Deg : 0f;
            }
            waveTell.center = p.transform.position;
            waveTell.progress = Mathf.Clamp01((projectileLead - eta) / (projectileLead - TellStyle.BiasParryable));
        }

        void Draw(Tell t)
        {
            // apoyado en el suelo (pendientes suaves), un poco arriba para no pelear con el terreno
            Vector3 pos = t.center;
            if (t.outcome == null && Physics.Raycast(pos + Vector3.up * 1.5f, Vector3.down, out var hit, 4f, 1, QueryTriggerInteraction.Ignore))
            {
                pos.y = hit.point.y;
                t.normal = Vector3.Angle(hit.normal, Vector3.up) < 35f ? hit.normal : Vector3.up;
                t.center = pos;
            }
            Vector3 n = t.normal;
            Vector3 fwd = Vector3.ProjectOnPlane(Quaternion.Euler(0f, t.yaw, 0f) * Vector3.forward, n);
            if (fwd.sqrMagnitude < 1e-4f) fwd = Vector3.forward;
            // el quad deja lugar para el halo de tinta, el punto de la punta y los pedazos que salen volando
            float half = t.radius * 1.7f + 0.3f;
            t.ring.SetPositionAndRotation(pos + n * 0.06f, Quaternion.LookRotation(fwd, n));
            t.ring.localScale = new Vector3(half * 2f, 1f, half * 2f);

            // al cerrarse: destello corto (más ancho, blanco). Después queda tenue hasta el golpe y se apaga:
            // el momento de apretar ya pasó y no tiene que tapar el aviso del siguiente
            bool closed = t.progress >= 1f;
            float flash = closed && t.outcome != TellOutcome.Parried && t.outcome != TellOutcome.Cancelled ? Mathf.Clamp01(1f - t.closedFor / FlashTime) : 0f;
            float alpha = closed && flash <= 0f && t.outcome != TellOutcome.Parried ? 0.45f : 1f;
            float width = strokeWidth * 0.5f * (t.danger ? 1.4f : 1f);
            // dorado casi todo el trazo; en el último tramo (ya dentro de la ventana del parry) se pone blanco
            float hot = Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(0.8f, 1f, t.progress)) * (t.danger ? 0.5f : 1f);

            mpb.Clear();
            mpb.SetColor(IdColor, t.danger ? TellStyle.Crimson : TellStyle.Gold);
            mpb.SetColor(IdHotColor, t.danger ? DangerHot : TellStyle.GoldHot);
            mpb.SetColor(IdInk, TellStyle.Ink);
            mpb.SetFloat(IdMode, 0f);
            mpb.SetFloat(IdProgress, t.progress);
            mpb.SetFloat(IdHot, hot);
            mpb.SetFloat(IdFlash, flash);
            mpb.SetFloat(IdDanger, t.danger ? 1f : 0f);
            mpb.SetFloat(IdAlpha, alpha);
            mpb.SetFloat(IdRadius, t.radius / half);
            mpb.SetFloat(IdWidth, width / half);
            mpb.SetFloat(IdDot, 0.125f / half);
            mpb.SetFloat(IdMinPx, minPixels * (t.danger ? 1.4f : 1f));
            mpb.SetFloat(IdOutcome, t.outcome == null ? 0f : t.outcome == TellOutcome.Parried ? 1f : t.outcome == TellOutcome.Cancelled ? 2f : 3f);
            mpb.SetFloat(IdOutT, t.outT);
            mpb.SetFloat(IdSeed, t.seed);
            t.ringR.SetPropertyBlock(mpb);

            // zona real del golpe (solo especiales imparables): se llena al ritmo del anillo
            t.areaR.enabled = t.hasArea;
            if (!t.hasArea) return;
            var a = t.areaShape;
            float ay = pos.y + 0.05f;
            if (a.lane)
            {
                Vector3 dir = a.forward.sqrMagnitude > 1e-4f ? a.forward : Vector3.forward;
                Vector3 c = a.origin + dir * (a.size * 0.5f); c.y = ay;
                t.area.SetPositionAndRotation(c, Quaternion.LookRotation(dir, Vector3.up));
                t.area.localScale = new Vector3(a.width * 1.1f, 1f, a.size * 1.04f);
                mpb.SetFloat(IdMode, 2f);
                mpb.SetFloat(IdRadius, 1f / 1.1f);    // bordes laterales
                mpb.SetFloat(IdWidth, 1f / 1.04f);    // fin del carril
            }
            else
            {
                Vector3 c = a.origin; c.y = ay;
                t.area.SetPositionAndRotation(c, Quaternion.identity);
                t.area.localScale = new Vector3(a.size * 2.12f, 1f, a.size * 2.12f);
                mpb.SetFloat(IdMode, 1f);
                mpb.SetFloat(IdRadius, 1f / 1.06f);
            }
            mpb.SetColor(IdColor, TellStyle.Crimson);
            mpb.SetFloat(IdAlpha, 1f);
            t.areaR.SetPropertyBlock(mpb);
        }

        void Show(Tell t, bool v)
        {
            if (t.visible == v) return;
            t.visible = v;
            t.ringR.enabled = v;
            if (!v) t.areaR.enabled = false;
        }

        Tell Acquire()
        {
            Tell t = pool.Count > 0 ? pool[pool.Count - 1] : null;
            if (t != null) pool.RemoveAt(pool.Count - 1);
            else
            {
                t = new Tell();
                t.ring = NewQuad("Enso", out t.ringR);
                t.area = NewQuad("EnsoArea", out t.areaR);
            }
            t.e = null; t.outcome = null; t.progress = 0f; t.closedFor = 0f; t.outT = 0f; t.hasArea = false;
            t.danger = false; t.normal = Vector3.up; t.visible = true;
            Show(t, false);
            active.Add(t);
            return t;
        }

        Transform NewQuad(string name, out MeshRenderer mr)
        {
            var go = new GameObject(name);
            go.transform.SetParent(transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = quad;
            mr = go.AddComponent<MeshRenderer>();
            mr.sharedMaterial = mat;
            mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            mr.receiveShadows = false;
            mr.enabled = false;
            return go.transform;
        }

        void Release(Tell t)
        {
            if (t.e != null && drawing.TryGetValue(t.e, out var cur) && cur == t) drawing.Remove(t.e);
            if (t == waveTell) waveTell = null;
            Show(t, false);
            t.e = null;
            active.Remove(t);
            pool.Add(t);
        }
    }
}
