using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>Encuentra (o crea) los puntos base/punta de la katana a partir del mesh del arma.</summary>
    public static class KatanaRig
    {
        public static bool Find(Transform root, string[] names, out Transform basePt, out Transform tipPt)
        {
            basePt = null; tipPt = null;
            if (root == null) return false;
            Renderer weapon = null;
            foreach (var r in root.GetComponentsInChildren<Renderer>(true))
            {
                foreach (var n in names)
                    if (r.gameObject.name.Contains(n)) { weapon = r; break; }
                if (weapon != null) break;
            }
            if (weapon == null) return false;
            Mesh mesh = null;
            if (weapon is SkinnedMeshRenderer smr) mesh = smr.sharedMesh;
            else if (weapon.GetComponent<MeshFilter>() is MeshFilter mf) mesh = mf.sharedMesh;
            if (mesh == null) return false;
            Bounds b = mesh.bounds;
            // eje más largo = hoja
            Vector3 axis = Vector3.right; float len = b.size.x;
            if (b.size.y > len) { axis = Vector3.up; len = b.size.y; }
            if (b.size.z > len) { axis = Vector3.forward; len = b.size.z; }
            Vector3 a = b.center - axis * len * 0.5f;
            Vector3 c = b.center + axis * len * 0.5f;
            // la punta es el extremo más lejano del origen del arma (la empuñadura está en la mano)
            if (a.sqrMagnitude > c.sqrMagnitude) { var t = a; a = c; c = t; }
            var tb = weapon.transform;
            basePt = new GameObject("KatanaBase").transform;
            basePt.SetParent(tb, false);
            basePt.localPosition = Vector3.Lerp(a, c, 0.22f);
            tipPt = new GameObject("KatanaTip").transform;
            tipPt.SetParent(tb, false);
            tipPt.localPosition = c;
            return true;
        }
    }

    /// <summary>
    /// Estela del arma (reescritura de SwordTrail): malla dinámica reutilizada, sin
    /// allocations por frame, con fade y color configurable (dorado normal / naranja en furia).
    /// </summary>
    public class BladeTrail : MonoBehaviour
    {
        Transform baseT, tipT;
        Mesh mesh;
        MeshRenderer mr;
        const int MaxPoints = 18;
        readonly Vector3[] tips = new Vector3[MaxPoints];
        readonly Vector3[] bases = new Vector3[MaxPoints];
        readonly float[] times = new float[MaxPoints];
        int count;
        bool emitting;
        float lifetime = 0.16f;
        Color color = Color.white;
        Vector3[] verts = new Vector3[MaxPoints * 2];
        Color[] cols = new Color[MaxPoints * 2];
        Vector2[] uvs = new Vector2[MaxPoints * 2];
        int[] tris = new int[(MaxPoints - 1) * 6];
        MaterialPropertyBlock mpb;

        public static BladeTrail Create(Transform owner, Transform basePt, Transform tipPt, Material mat, Color c)
        {
            var go = new GameObject("BladeTrail");
            go.transform.SetParent(null, false);
            var t = go.AddComponent<BladeTrail>();
            t.baseT = basePt; t.tipT = tipPt; t.color = c;
            go.AddComponent<MeshFilter>().sharedMesh = t.mesh = new Mesh { name = "BladeTrail" };
            t.mesh.MarkDynamic();
            t.mr = go.AddComponent<MeshRenderer>();
            t.mr.sharedMaterial = mat != null ? mat : FXMaterials.Additive;
            t.mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            t.mr.receiveShadows = false;
            var follow = go.AddComponent<FollowLifetime>();
            follow.owner = owner;
            return t;
        }

        public void Begin() { emitting = true; count = 0; }
        public void Stop() { emitting = false; }
        public void SetColor(Color c) { color = c; }

        void LateUpdate()
        {
            if (baseT == null || tipT == null) { Destroy(gameObject); return; }
            float now = Time.time;
            if (emitting)
            {
                if (count == MaxPoints) { System.Array.Copy(tips, 1, tips, 0, MaxPoints - 1); System.Array.Copy(bases, 1, bases, 0, MaxPoints - 1); System.Array.Copy(times, 1, times, 0, MaxPoints - 1); count--; }
                tips[count] = tipT.position; bases[count] = baseT.position; times[count] = now; count++;
            }
            // quitar puntos viejos
            int drop = 0;
            while (drop < count && now - times[drop] > lifetime) drop++;
            if (drop > 0)
            {
                System.Array.Copy(tips, drop, tips, 0, count - drop);
                System.Array.Copy(bases, drop, bases, 0, count - drop);
                System.Array.Copy(times, drop, times, 0, count - drop);
                count -= drop;
            }
            mesh.Clear();
            if (count < 2) return;
            for (int i = 0; i < count; i++)
            {
                float a = 1f - (now - times[i]) / lifetime;
                float along = (float)i / (count - 1);
                verts[i * 2] = bases[i];
                verts[i * 2 + 1] = tips[i];
                Color c = color; c.a *= Mathf.Clamp01(a) * along;
                cols[i * 2] = c * new Color(1, 1, 1, 0.35f);
                cols[i * 2 + 1] = c;
                uvs[i * 2] = new Vector2(along, 0); uvs[i * 2 + 1] = new Vector2(along, 1);
            }
            int ti = 0;
            for (int i = 0; i < count - 1; i++)
            {
                int v = i * 2;
                tris[ti++] = v; tris[ti++] = v + 1; tris[ti++] = v + 2;
                tris[ti++] = v + 1; tris[ti++] = v + 3; tris[ti++] = v + 2;
            }
            mesh.SetVertices(verts, 0, count * 2);
            mesh.SetColors(cols, 0, count * 2);
            mesh.SetUVs(0, uvs, 0, count * 2);
            mesh.SetTriangles(tris, 0, (count - 1) * 6, 0, false);
            mesh.RecalculateBounds();
        }
    }

    /// <summary>Destruye un objeto "suelto" (estelas en espacio mundo) cuando muere su dueño.</summary>
    public class FollowLifetime : MonoBehaviour
    {
        public Transform owner;
        void Update() { if (owner == null) Destroy(gameObject); }
    }

    /// <summary>Fuego en la katana durante "Filo de Ira".</summary>
    public class KatanaFire : MonoBehaviour
    {
        ParticleSystem ps;
        Light glow;

        public static KatanaFire Create(Transform basePt, Transform tipPt)
        {
            var go = new GameObject("KatanaFire");
            go.transform.SetParent(basePt, false);
            var kf = go.AddComponent<KatanaFire>();
            Vector3 local = basePt.InverseTransformPoint(tipPt.position);
            kf.ps = FXFactory.FireAlongBlade(go.transform, local);
            var lg = new GameObject("FireLight");
            lg.transform.SetParent(go.transform, false);
            lg.transform.localPosition = local * 0.5f;
            kf.glow = lg.AddComponent<Light>();
            kf.glow.type = LightType.Point; kf.glow.color = new Color(1f, 0.55f, 0.2f); kf.glow.range = 4f; kf.glow.intensity = 2.5f;
            kf.glow.shadows = LightShadows.None;
            kf.SetActive(false);
            return kf;
        }

        public void SetActive(bool on)
        {
            if (ps != null) { if (on) ps.Play(); else ps.Stop(); }
            if (glow != null) glow.enabled = on;
        }

        void Update()
        {
            if (glow != null && glow.enabled) glow.intensity = 2.2f + Mathf.PerlinNoise(Time.time * 9f, 0.3f) * 1.4f;
        }
    }

    /// <summary>Destello blanco al recibir daño: cambia los materiales un instante (no necesita shaders especiales).</summary>
    public class HitFlash : MonoBehaviour
    {
        Renderer[] renderers;
        Material[][] originals;
        float until;
        bool flashing;

        public static HitFlash Attach(GameObject go)
        {
            var h = go.GetComponent<HitFlash>();
            if (h == null) h = go.AddComponent<HitFlash>();
            return h;
        }

        void Awake() => Cache();

        void Cache()
        {
            var list = new List<Renderer>();
            foreach (var r in GetComponentsInChildren<Renderer>(true))
                if (r is SkinnedMeshRenderer || r is MeshRenderer) list.Add(r);
            renderers = list.ToArray();
            originals = new Material[renderers.Length][];
        }

        public void Flash(float seconds = 0.07f)
        {
            if (renderers == null) Cache();
            var m = Game.Content != null && Game.Content.flashMaterial != null ? Game.Content.flashMaterial : FXMaterials.Flash;
            if (!flashing)
            {
                for (int i = 0; i < renderers.Length; i++)
                {
                    if (renderers[i] == null) continue;
                    originals[i] = renderers[i].sharedMaterials;
                    var arr = new Material[originals[i].Length];
                    for (int k = 0; k < arr.Length; k++) arr[k] = m;
                    renderers[i].sharedMaterials = arr;
                }
            }
            flashing = true;
            until = Time.unscaledTime + seconds;
        }

        void LateUpdate()
        {
            if (!flashing || Time.unscaledTime < until) return;
            flashing = false;
            for (int i = 0; i < renderers.Length; i++)
                if (renderers[i] != null && originals[i] != null) renderers[i].sharedMaterials = originals[i];
        }

        void OnDisable()
        {
            if (flashing) { until = 0f; LateUpdate(); }
        }
    }

    /// <summary>
    /// Movimiento procedural sutil que da vida a las animaciones: inclinación al correr y al
    /// girar, y un pequeño "squash" en el dash. Se aplica sobre el hijo del modelo.
    /// </summary>
    public class ProceduralMotion : MonoBehaviour
    {
        public float leanAngle = 9f;
        public float turnRoll = 10f;
        /// <summary>
        /// Pose guionada del pivote (p. ej. Kaito tirado en el piso en el prólogo). El pivote es de
        /// este componente y se reescribe en cada LateUpdate, así que las cinemáticas no lo rotan
        /// directo: ponen la pose acá y se compone con la inclinación. identity = sin pose.
        /// </summary>
        public Quaternion scriptedPose = Quaternion.identity;
        PlayerController pc;
        Transform pivot;
        Vector3 lastFwd;
        float lean, roll;

        void Start()
        {
            pc = GetComponent<PlayerController>();
            if (pc != null && pc.model != null)
            {
                // insertamos un pivote entre la raíz y el modelo para no pelear con el Animator
                pivot = new GameObject("LeanPivot").transform;
                pivot.SetParent(transform, false);
                pc.model.SetParent(pivot, true);
            }
            lastFwd = transform.forward;
        }

        void LateUpdate()
        {
            if (pivot == null || pc == null) return;
            float dt = Time.deltaTime;
            if (dt <= 0f) return;
            bool moving = pc.State == PlayerState.Locomotion;
            float speed01 = moving ? Mathf.Clamp01(pc.Velocity.magnitude / pc.config.runSpeed) : 0f;
            float yawRate = Vector3.SignedAngle(lastFwd, transform.forward, Vector3.up) / dt;
            lastFwd = transform.forward;
            float targetLean = moving ? speed01 * leanAngle : 0f;
            float targetRoll = moving ? Mathf.Clamp(-yawRate * 0.02f, -1f, 1f) * turnRoll * speed01 : 0f;
            if (pc.State == PlayerState.Dash) targetLean = 16f;
            lean = CombatMath.Damp(lean, targetLean, 10f, dt);
            roll = CombatMath.Damp(roll, targetRoll, 8f, dt);
            pivot.localRotation = scriptedPose * Quaternion.Euler(lean, 0f, roll);
            float sq = pc.State == PlayerState.Dash ? 0.06f : 0f;
            pivot.localScale = CombatMath.Damp(pivot.localScale, new Vector3(1f - sq * 0.5f, 1f - sq, 1f + sq), 14f, dt);
        }
    }
}
