using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Zonas de golpe de Mizuchi apoyadas en el mundo, con el mismo pincel que los avisos del resto del juego (shader
    /// Nindo/Telegraph, modos disco y carril): CombatTelegraphs dibuja una sola zona por atacante y el koi necesita
    /// varias a la vez (cuatro pilares, la franja de la ola con sus huecos, el abanico del chorro barrido) y en lugares
    /// donde él no está (cae del cielo, sale del agua). Mismo idioma: rojo = salí de ahí, se llena al ritmo del golpe y
    /// se apaga al pegar. Un quad por zona y un MaterialPropertyBlock por frame; se reciclan.
    /// </summary>
    public class MizuchiMarks : MonoBehaviour
    {
        public class Mark
        {
            internal Transform tf;
            internal MeshRenderer mr;
            internal bool lane, active;
            internal Vector3 origin, forward = Vector3.forward;
            internal float size, width, alpha = 1f, seed, outT;
            internal int outcome;   // 0 dibujando, 2 cortado, 3 golpe (como el shader)
            internal Color color;
            public float Progress;
            /// <summary>Mueve el carril (el chorro mientras apunta).</summary>
            public void Aim(Vector3 from, Vector3 dir, float length) { origin = from; forward = dir.Flat().normalized; size = length; }
            public void Move(Vector3 center) => origin = center;
            public void SetAlpha(float a) => alpha = Mathf.Clamp01(a);
            public void SetColor(Color c) => color = c;
        }

        static readonly int IdColor = Shader.PropertyToID("_Color"), IdHotColor = Shader.PropertyToID("_HotColor"), IdInk = Shader.PropertyToID("_Ink"),
            IdMode = Shader.PropertyToID("_Mode"), IdProgress = Shader.PropertyToID("_Progress"), IdDanger = Shader.PropertyToID("_Danger"),
            IdAlpha = Shader.PropertyToID("_Alpha"), IdRadius = Shader.PropertyToID("_Radius"), IdWidth = Shader.PropertyToID("_Width"),
            IdMinPx = Shader.PropertyToID("_MinPx"), IdOutcome = Shader.PropertyToID("_Outcome"), IdOutT = Shader.PropertyToID("_OutT"),
            IdSeed = Shader.PropertyToID("_Seed");
        const float OutTime = 0.18f;

        readonly List<Mark> marks = new List<Mark>();
        Mesh quad;
        Material mat;
        MaterialPropertyBlock mpb;

        // abanico (chorro barrido): relleno plano que crece desde la boca; los bordes los pintan dos carriles finos.
        // Un abanico de 7 carriles cruzaba 14 bordes en la boca y se leía como una telaraña (render de prueba)
        Transform wedge;
        MeshRenderer wedgeR;
        Mesh wedgeMesh;
        Material wedgeMat;
        MaterialPropertyBlock wedgeMpb;
        float wedgeAlpha, wedgeTarget, wedgeRadius;
        /// <summary>Cuánto del abanico está pintado desde la boca (0..1).</summary>
        public float WedgeProgress { get; set; }

        public static MizuchiMarks Create()
        {
            var go = new GameObject("[MizuchiMarks]");
            var m = go.AddComponent<MizuchiMarks>();
            m.Build();
            return m;
        }

        void Build()
        {
            var sh = Resources.Load<Shader>("Shaders/NindoTelegraph");
            if (sh == null || !sh.isSupported) { enabled = false; return; }
            mat = new Material(sh) { name = "MizuchiMarks" };
            mpb = new MaterialPropertyBlock();
            quad = new Mesh { name = "MarkQuad" };
            quad.vertices = new[] { new Vector3(-0.5f, 0, -0.5f), new Vector3(0.5f, 0, -0.5f), new Vector3(-0.5f, 0, 0.5f), new Vector3(0.5f, 0, 0.5f) };
            quad.uv = new[] { new Vector2(0, 0), new Vector2(1, 0), new Vector2(0, 1), new Vector2(1, 1) };
            quad.triangles = new[] { 0, 2, 1, 2, 3, 1 };
            quad.RecalculateBounds();
        }

        void OnDestroy()
        {
            if (mat != null) Destroy(mat);
            if (quad != null) Destroy(quad);
            if (wedgeMesh != null) Destroy(wedgeMesh);
            if (wedgeMat != null) Destroy(wedgeMat);
        }

        /// <summary>Muestra el abanico rojo con vértice en 'apex', centrado en 'dir', de 'radius' m y ±'halfAngle'°.</summary>
        public void ShowWedge(Vector3 apex, Vector3 dir, float radius, float halfAngle)
        {
            if (wedge == null)
            {
                const int Seg = 16;
                var v = new Vector3[Seg + 2];
                var tri = new int[Seg * 3];
                v[0] = Vector3.zero;
                for (int i = 0; i <= Seg; i++)
                {
                    float a = Mathf.Lerp(-halfAngle, halfAngle, i / (float)Seg) * Mathf.Deg2Rad;
                    v[i + 1] = new Vector3(Mathf.Sin(a), 0f, Mathf.Cos(a));
                }
                for (int i = 0; i < Seg; i++) { tri[i * 3] = 0; tri[i * 3 + 1] = i + 1; tri[i * 3 + 2] = i + 2; }
                wedgeMesh = new Mesh { name = "MarkWedge", vertices = v, triangles = tri };
                wedgeMesh.RecalculateBounds();
                var go = new GameObject("Wedge");
                go.transform.SetParent(transform, false);
                go.AddComponent<MeshFilter>().sharedMesh = wedgeMesh;
                wedgeR = go.AddComponent<MeshRenderer>();
                wedgeMat = FXMaterials.MakeUnlitTransparent("MarkWedge", TellStyle.Crimson, false);
                wedgeR.sharedMaterial = wedgeMat;
                wedgeR.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                wedgeR.receiveShadows = false;
                wedgeMpb = new MaterialPropertyBlock();
                wedge = go.transform;
            }
            wedge.SetPositionAndRotation(apex + Vector3.up * 0.05f, Quaternion.LookRotation(dir.Flat().normalized, Vector3.up));
            wedgeRadius = radius;
            WedgeProgress = 0f;
            wedgeTarget = 1f;
            wedgeAlpha = 0f;
            wedgeR.enabled = true;
        }

        public void HideWedge() => wedgeTarget = 0f;

        /// <summary>Disco rojo de radio 'radius' apoyado en 'center' (y = altura del piso).</summary>
        public Mark Disc(Vector3 center, float radius)
        {
            var m = Acquire();
            m.lane = false; m.origin = center; m.size = radius; m.width = 0f;
            return m;
        }

        /// <summary>Carril desde 'from' hacia 'dir' de 'length' x 'width' (m), del color pedido.</summary>
        public Mark Lane(Vector3 from, Vector3 dir, float length, float width, Color color)
        {
            var m = Acquire();
            m.lane = true; m.Aim(from, dir, length); m.width = width; m.color = color;
            return m;
        }

        /// <summary>Termina la zona: 'struck' = pegó (se apaga), si no se deshace como un golpe cortado.</summary>
        public void Finish(Mark m, bool struck)
        {
            if (m == null || !m.active || m.outcome != 0) return;
            m.outcome = struck ? 3 : 2;
            m.outT = 0f;
            if (struck) m.Progress = 1f;
        }

        /// <summary>Borra todo ya (reintento, cambio de fase).</summary>
        public void Clear()
        {
            foreach (var m in marks) { m.active = false; if (m.mr != null) m.mr.enabled = false; }
            if (wedgeR != null) { wedgeR.enabled = false; wedgeAlpha = wedgeTarget = 0f; }
        }

        Mark Acquire()
        {
            Mark m = null;
            foreach (var x in marks) if (!x.active) { m = x; break; }
            if (m == null)
            {
                m = new Mark();
                var go = new GameObject("Mark");
                go.transform.SetParent(transform, false);
                go.AddComponent<MeshFilter>().sharedMesh = quad;
                m.mr = go.AddComponent<MeshRenderer>();
                m.mr.sharedMaterial = mat;
                m.mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                m.mr.receiveShadows = false;
                m.tf = go.transform;
                marks.Add(m);
            }
            m.active = true; m.outcome = 0; m.outT = 0f; m.Progress = 0f; m.alpha = 1f;
            m.color = TellStyle.Crimson; m.seed = Random.value * 10f;
            m.mr.enabled = mat != null;
            return m;
        }

        void LateUpdate()
        {
            if (mat == null) return;
            float dt = Time.deltaTime;
            if (wedgeR != null && wedgeR.enabled)
            {
                // entra en 0.1 s y se apaga en 0.2 s; crece desde la boca al ritmo del aviso
                wedgeAlpha = Mathf.MoveTowards(wedgeAlpha, wedgeTarget, dt / (wedgeTarget > wedgeAlpha ? 0.1f : 0.2f));
                if (wedgeAlpha <= 0f && wedgeTarget <= 0f) wedgeR.enabled = false;
                else
                {
                    float r = wedgeRadius * Mathf.Lerp(0.15f, 1f, Mathf.Clamp01(WedgeProgress));
                    wedge.localScale = new Vector3(r, 1f, r);
                    Color c = TellStyle.Crimson; c.a = (0.16f + 0.2f * Mathf.Clamp01(WedgeProgress)) * wedgeAlpha;
                    wedgeMpb.SetColor("_BaseColor", c);
                    wedgeMpb.SetColor("_Color", c);
                    wedgeR.SetPropertyBlock(wedgeMpb);
                }
            }
            foreach (var m in marks)
            {
                if (!m.active) continue;
                if (m.outcome != 0)
                {
                    m.outT += dt / OutTime;
                    if (m.outT >= 1f) { m.active = false; m.mr.enabled = false; continue; }
                }
                Draw(m);
            }
        }

        void Draw(Mark m)
        {
            mpb.Clear();
            mpb.SetColor(IdColor, m.color);
            mpb.SetColor(IdHotColor, m.color);
            mpb.SetColor(IdInk, TellStyle.Ink);
            mpb.SetFloat(IdProgress, Mathf.Clamp01(m.Progress));
            mpb.SetFloat(IdDanger, 1f);
            mpb.SetFloat(IdAlpha, m.alpha);
            mpb.SetFloat(IdMinPx, 16f);
            mpb.SetFloat(IdOutcome, m.outcome);
            mpb.SetFloat(IdOutT, m.outT);
            mpb.SetFloat(IdSeed, m.seed);
            Vector3 p = m.origin + Vector3.up * 0.06f;
            if (m.lane)
            {
                Vector3 dir = m.forward.sqrMagnitude > 1e-4f ? m.forward : Vector3.forward;
                m.tf.SetPositionAndRotation(p + dir * (m.size * 0.5f), Quaternion.LookRotation(dir, Vector3.up));
                m.tf.localScale = new Vector3(m.width * 1.1f, 1f, m.size * 1.04f);
                mpb.SetFloat(IdMode, 2f);
                mpb.SetFloat(IdRadius, 1f / 1.1f);    // bordes laterales
                mpb.SetFloat(IdWidth, 1f / 1.04f);    // fin del carril
            }
            else
            {
                m.tf.SetPositionAndRotation(p, Quaternion.identity);
                m.tf.localScale = new Vector3(m.size * 2.12f, 1f, m.size * 2.12f);
                mpb.SetFloat(IdMode, 1f);
                mpb.SetFloat(IdRadius, 1f / 1.06f);
            }
            m.mr.SetPropertyBlock(mpb);
        }
    }
}
