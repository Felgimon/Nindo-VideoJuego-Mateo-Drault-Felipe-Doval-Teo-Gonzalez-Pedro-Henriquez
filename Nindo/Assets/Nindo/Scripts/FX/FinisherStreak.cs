using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Tajo de tres franjas del remate (shader Nindo/InkStreak): sigue la trayectoria de Kaito al atravesar al
    /// enemigo, en la dirección que sea. Un quad que mira a la cámara, del punto de arranque al de llegada
    /// (estirado un poco a cada lado): se pinta de punta a punta en 0.07 s, queda un instante y se borra desde
    /// el arranque como la estela del movimiento. Corre en tiempo real: el remate trae hit-stop y cámara lenta.
    /// </summary>
    public class FinisherStreak : MonoBehaviour
    {
        // fino y largo: con 0.95 m de ancho y poco recorrido parecía una espada tirada en el piso, no una estela
        const float PaintTime = 0.07f, HoldTime = 0.1f, EraseTime = 0.34f, BackOvershoot = 0.5f, FrontOvershoot = 1.5f, Width = 0.58f;

        static readonly Stack<FinisherStreak> free = new Stack<FinisherStreak>();
        static Material mat;
        static readonly int IdHead = Shader.PropertyToID("_Head"), IdTail = Shader.PropertyToID("_Tail"),
            IdGold = Shader.PropertyToID("_Gold"), IdSeed = Shader.PropertyToID("_Seed");

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetPool() => free.Clear();

        Mesh mesh;
        MeshRenderer mr;
        MaterialPropertyBlock mpb;
        readonly Vector3[] verts = new Vector3[4];
        Vector3 a, b;
        float t;

        /// <summary>Tajo de 'from' a 'to' (a la altura del pecho). Con el Filo de Ira el filo sale anaranjado.</summary>
        public static void Spawn(Vector3 from, Vector3 to, bool rage)
        {
            if (mat == null)
            {
                var sh = Resources.Load<Shader>("Shaders/NindoInkStreak");
                if (sh == null || !sh.isSupported) return;
                mat = new Material(sh) { name = "InkStreak" };
            }
            FinisherStreak s = null;
            while (s == null && free.Count > 0) s = free.Pop();
            if (s == null)
            {
                var go = new GameObject("FinisherStreak");
                s = go.AddComponent<FinisherStreak>();
                s.mesh = new Mesh { name = "FinisherStreak" };
                s.mesh.MarkDynamic();
                s.mesh.vertices = s.verts;
                s.mesh.uv = new[] { new Vector2(0, 0), new Vector2(0, 1), new Vector2(1, 0), new Vector2(1, 1) };
                s.mesh.triangles = new[] { 0, 1, 2, 2, 1, 3 };
                go.AddComponent<MeshFilter>().sharedMesh = s.mesh;
                s.mr = go.AddComponent<MeshRenderer>();
                s.mr.sharedMaterial = mat;
                s.mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                s.mr.receiveShadows = false;
                s.mpb = new MaterialPropertyBlock();
            }
            Vector3 dir = to - from;
            if (dir.sqrMagnitude < 1e-4f) dir = Vector3.forward;
            dir.Normalize();
            s.a = from - dir * BackOvershoot;
            s.b = to + dir * FrontOvershoot;
            s.t = 0f;
            s.mpb.Clear();
            s.mpb.SetColor(IdGold, rage ? new Color(1f, 0.45f, 0.14f) : new Color(1f, 0.8f, 0.34f));
            s.mpb.SetFloat(IdSeed, Random.value * 10f);
            s.gameObject.SetActive(true);
            s.UpdateShape();
        }

        void LateUpdate()
        {
            t += Time.unscaledDeltaTime;
            if (t >= PaintTime + HoldTime + EraseTime) { gameObject.SetActive(false); free.Push(this); return; }
            UpdateShape();
        }

        void UpdateShape()
        {
            // mira a la cámara alrededor de su propio eje (sigue viéndose ancho aunque la cámara se mueva en el remate)
            var cam = Game.Camera != null ? Game.Camera.Cam : Camera.main;
            Vector3 axis = b - a;
            Vector3 view = cam != null ? (cam.transform.position - (a + b) * 0.5f) : Vector3.up;
            Vector3 side = Vector3.Cross(axis, view).normalized;
            if (side.sqrMagnitude < 1e-4f) side = Vector3.Cross(axis, Vector3.up).normalized;
            // un poco más ancho a medida que se borra (la tinta se abre)
            float erase = Mathf.Clamp01((t - PaintTime - HoldTime) / EraseTime);
            float half = Width * 0.5f * (1f + 0.25f * erase);
            transform.position = Vector3.zero;
            transform.rotation = Quaternion.identity;
            verts[0] = a - side * half; verts[1] = a + side * half;
            verts[2] = b - side * half; verts[3] = b + side * half;
            mesh.vertices = verts;
            mesh.RecalculateBounds();

            float head = 1f - Mathf.Pow(1f - Mathf.Clamp01(t / PaintTime), 3f);   // sale disparado y frena
            mpb.SetFloat(IdHead, head);
            mpb.SetFloat(IdTail, erase * erase);                                    // la estela se acelera al irse
            mr.SetPropertyBlock(mpb);
        }
    }
}
