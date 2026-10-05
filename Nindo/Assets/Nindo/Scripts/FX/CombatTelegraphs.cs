using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Avisos de ataque en el suelo: el jugador tiene que saber CUÁNDO pega cada enemigo para hacer
    /// parry, y desde la cámara alta la anticipación de la animación no alcanza.
    /// Por cada enemigo que está por pegar se dibuja (shader Nindo/Telegraph) la zona que golpea y un
    /// anillo que se cierra sobre el anillo de los pies exactamente en el impacto (Enemy.StrikeEta),
    /// con destello blanco dentro de la ventana del parry. Dorado = desviable; rojo dentado = imparable.
    /// </summary>
    public class CombatTelegraphs : MonoBehaviour
    {
        class Indicator
        {
            public Enemy e;
            public Transform tr;
            public MeshRenderer mr;
            public AttackDef atk;
            public float eta0, lastEta, fade;
            public bool seen;
        }

        [Tooltip("Desde cuántos segundos antes del golpe aparece el aviso")] public float showLead = 1.4f;
        [Tooltip("Ventana para el dash contra imparables (s antes del golpe)")] public float dashWindow = 0.3f;

        readonly List<Indicator> pool = new List<Indicator>();
        readonly Dictionary<Enemy, Indicator> byEnemy = new Dictionary<Enemy, Indicator>();
        Mesh quad;
        Material mat;
        MaterialPropertyBlock mpb;

        static readonly int IdColor = Shader.PropertyToID("_Color"), IdProgress = Shader.PropertyToID("_Progress"),
            IdWindow = Shader.PropertyToID("_Window"), IdDanger = Shader.PropertyToID("_Danger"), IdAlpha = Shader.PropertyToID("_Alpha"),
            IdRingR = Shader.PropertyToID("_RingR"), IdShape = Shader.PropertyToID("_Shape"), IdArcHalf = Shader.PropertyToID("_ArcHalf"),
            IdRange = Shader.PropertyToID("_Range"), IdOffset = Shader.PropertyToID("_Offset"), IdWidth = Shader.PropertyToID("_Width");

        static readonly Color ParryColor = new Color(1f, 0.8f, 0.32f), DangerColor = new Color(1f, 0.16f, 0.1f);

        void Awake()
        {
            var sh = Resources.Load<Shader>("Shaders/NindoTelegraph");
            if (sh == null || !sh.isSupported) { enabled = false; return; }
            mat = new Material(sh) { name = "Telegraph", enableInstancing = true };
            mpb = new MaterialPropertyBlock();
            quad = new Mesh { name = "TelegraphQuad" };
            quad.vertices = new[] { new Vector3(-0.5f, 0, -0.5f), new Vector3(0.5f, 0, -0.5f), new Vector3(-0.5f, 0, 0.5f), new Vector3(0.5f, 0, 0.5f) };
            quad.uv = new[] { new Vector2(0, 0), new Vector2(1, 0), new Vector2(0, 1), new Vector2(1, 1) };
            quad.triangles = new[] { 0, 2, 1, 2, 3, 1 };
            quad.RecalculateBounds();
        }

        void OnDestroy()
        {
            if (mat != null) Destroy(mat);
            if (quad != null) Destroy(quad);
        }

        void LateUpdate()
        {
            for (int i = 0; i < pool.Count; i++) pool[i].seen = false;
            var cd = Game.Combat;
            if (cd != null && Game.Player != null && Game.Player.IsAlive && !Game.InCutscene)
            {
                var list = cd.Engaged;
                for (int i = 0; i < list.Count; i++) Consider(list[i]);
                var boss = cd.ActiveBoss;
                if (boss != null && !byEnemy.ContainsKey(boss)) Consider(boss);
            }
            float dt = Time.deltaTime;
            for (int i = 0; i < pool.Count; i++)
            {
                var ind = pool[i];
                if (ind.e == null) continue;
                if (!ind.seen)
                {
                    // el golpe salió (o se cortó): se apaga rápido
                    ind.fade = Mathf.MoveTowards(ind.fade, 0f, dt * 7f);
                    mpb.Clear();
                    ind.mr.GetPropertyBlock(mpb);
                    mpb.SetFloat(IdAlpha, ind.fade);
                    ind.mr.SetPropertyBlock(mpb);
                    if (ind.fade <= 0f) Release(ind);
                }
            }
        }

        void Consider(Enemy e)
        {
            if (e == null || !e.IsAlive) return;
            var a = e.CurrentAttack;
            float eta = e.StrikeEta;
            if (a == null || float.IsInfinity(eta) || eta > showLead) return;
            if (!byEnemy.TryGetValue(e, out var ind)) ind = Acquire(e);
            // golpe nuevo (otro paso del combo o recién aparece): eta vuelve a subir
            if (ind.atk != a || eta > ind.lastEta + 0.03f || ind.fade <= 0f) { ind.eta0 = Mathf.Max(eta, 0.2f); ind.atk = a; }
            ind.lastEta = eta;
            ind.seen = true;
            ind.fade = Mathf.MoveTowards(ind.fade, 1f, Time.deltaTime * 9f);

            bool danger = a.kind == AttackKind.Unblockable;
            var p = Game.Player;
            float window = danger ? dashWindow : (p != null ? p.config.parryWindow : 0.24f);
            float prog = Mathf.Clamp01(1f - eta / ind.eta0);

            // ---- forma y tamaño (metros)
            float ringW = e.Radius * 1.5f + 0.35f;
            float shape = 0f, reach = Mathf.Max(e.StrikeReach, a.range), arcHalf = a.arc * 0.5f * Mathf.Deg2Rad, offset = 0f, width = 0f;
            switch (a.special)
            {
                case "slam":
                    shape = 1f; offset = Mathf.Max(0.5f, a.range * 0.4f); reach = a.specialParam > 0f ? a.specialParam : 4f; break;
                case "spin":
                    shape = 1f; reach = a.range + 0.4f; break;
                case "charge":
                    shape = 2f; width = e.Radius + 0.45f;
                    reach = p != null ? Mathf.Min(18f, CombatMath.FlatDistance(p.transform.position, e.transform.position) + 2f) : 8f; break;
                case "windslash":
                    shape = 2f; width = 0.7f; reach = a.specialParam > 0f ? a.specialParam : 9f; break;
            }
            float half = Mathf.Max(ringW * 2.7f, shape > 0.5f && shape < 1.5f ? offset + reach : reach) + 0.4f;

            // ---- apoyado en el suelo, mirando hacia donde pega
            Vector3 pos = e.transform.position;
            Vector3 n = Vector3.up;
            if (Physics.Raycast(pos + Vector3.up * 1.5f, Vector3.down, out var hit, 4f, 1, QueryTriggerInteraction.Ignore))
            {
                pos.y = hit.point.y;
                if (Vector3.Angle(hit.normal, Vector3.up) < 35f) n = hit.normal;
            }
            Vector3 fwd = Vector3.ProjectOnPlane(e.transform.forward, n);
            if (fwd.sqrMagnitude < 1e-4f) fwd = Vector3.forward;
            ind.tr.SetPositionAndRotation(pos + n * 0.07f, Quaternion.LookRotation(fwd, n));
            ind.tr.localScale = new Vector3(half * 2f, 1f, half * 2f);

            mpb.Clear();
            mpb.SetColor(IdColor, danger ? DangerColor : ParryColor);
            mpb.SetFloat(IdProgress, prog);
            mpb.SetFloat(IdWindow, eta <= window ? 1f : 0f);
            mpb.SetFloat(IdDanger, danger ? 1f : 0f);
            mpb.SetFloat(IdAlpha, ind.fade * (0.7f + 0.3f * prog));
            mpb.SetFloat(IdRingR, ringW / half);
            mpb.SetFloat(IdShape, shape);
            mpb.SetFloat(IdArcHalf, Mathf.Clamp(arcHalf, 0.1f, Mathf.PI));
            mpb.SetFloat(IdRange, Mathf.Clamp01(reach / half));
            mpb.SetFloat(IdOffset, offset / half);
            mpb.SetFloat(IdWidth, width / half);
            ind.mr.SetPropertyBlock(mpb);
        }

        Indicator Acquire(Enemy e)
        {
            Indicator ind = null;
            foreach (var x in pool) if (x.e == null) { ind = x; break; }
            if (ind == null)
            {
                var go = new GameObject("Telegraph");
                go.transform.SetParent(transform, false);
                go.AddComponent<MeshFilter>().sharedMesh = quad;
                var mr = go.AddComponent<MeshRenderer>();
                mr.sharedMaterial = mat;
                mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                mr.receiveShadows = false;
                ind = new Indicator { tr = go.transform, mr = mr };
                pool.Add(ind);
            }
            ind.e = e; ind.atk = null; ind.fade = 0f; ind.lastEta = float.PositiveInfinity;
            ind.tr.gameObject.SetActive(true);
            byEnemy[e] = ind;
            return ind;
        }

        void Release(Indicator ind)
        {
            if (ind.e != null) byEnemy.Remove(ind.e);
            ind.e = null;
            ind.tr.gameObject.SetActive(false);
        }
    }
}
