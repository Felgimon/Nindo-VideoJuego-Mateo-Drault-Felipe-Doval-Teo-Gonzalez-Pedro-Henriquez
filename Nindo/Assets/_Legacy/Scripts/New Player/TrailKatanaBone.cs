using System.Collections.Generic;
using UnityEngine;

[RequireComponent(typeof(MeshFilter), typeof(MeshRenderer))]
public class SwordTrail : MonoBehaviour
{
    [Header("Referencias")]
    [SerializeField] private Transform tip;
    [SerializeField] private Transform baseSword;

    [Header("Configuración")]
    [SerializeField] private float pointLifetime = 0.4f;
    [SerializeField] private float minMovement = 0.001f;
    [SerializeField] private int maxPoints = 25;

    private class TrailPoint
    {
        public Vector3 tipPos;
        public Vector3 basePos;
        public float timeCreated;
    }

    private List<TrailPoint> points = new List<TrailPoint>();
    private Mesh mesh;

    [SerializeField] private bool trailActive = false;
    private bool stoppingTrail = false;
    private float fadeStartTime;

    private Vector3 lastTipPos;
    private Vector3 lastBasePos;

    void Start()
    {
        mesh = new Mesh();
        GetComponent<MeshFilter>().mesh = mesh;

        lastTipPos = tip.position;
        lastBasePos = baseSword.position;
    }

    void LateUpdate()
    {
        float time = Time.time;

        // Agregar puntos si el trail está activo
        if (trailActive && !stoppingTrail)
        {
            float tipMoved = Vector3.Distance(tip.position, lastTipPos);
            float baseMoved = Vector3.Distance(baseSword.position, lastBasePos);

            if (tipMoved > minMovement || baseMoved > minMovement)
            {
                points.Add(new TrailPoint
                {
                    tipPos = tip.position,
                    basePos = baseSword.position,
                    timeCreated = time
                });

                lastTipPos = tip.position;
                lastBasePos = baseSword.position;

                if (points.Count > maxPoints)
                    points.RemoveAt(0);
            }
        }

        // Si se detuvo el trail, forzar el fade de todos los puntos
        if (stoppingTrail)
        {
            float elapsed = time - fadeStartTime;
            float fadeRatio = elapsed / pointLifetime;

            if (fadeRatio >= 1f)
            {
                // Todos los puntos ya se desvanecieron completamente
                points.Clear();
                mesh.Clear();
                stoppingTrail = false;
                return;
            }
        }

        // Borrar puntos vencidos por lifetime (solo si el trail sigue activo)
        if (!stoppingTrail)
        {
            for (int i = points.Count - 1; i >= 0; i--)
            {
                if (time - points[i].timeCreated > pointLifetime)
                    points.RemoveAt(i);
            }
        }

        // Si hay menos de 2 puntos, limpiar el mesh
        if (points.Count < 2)
        {
            mesh.Clear();
            return;
        }

        // Generar el mesh
        Vector3[] vertices = new Vector3[points.Count * 2];
        Color[] colors = new Color[points.Count * 2];
        int[] triangles = new int[(points.Count - 1) * 6];

        for (int i = 0; i < points.Count; i++)
        {
            float age = time - points[i].timeCreated;
            float alpha = 1f - (age / pointLifetime);

            if (stoppingTrail)
            {
                float fadeProgress = (time - fadeStartTime) / pointLifetime;
                alpha = Mathf.Clamp01(1f - fadeProgress);
            }

            // Factor de escala según la edad del punto
            float t = (float)i / (points.Count - 1);
            // t = 0 → inicio del trail (fino)
            // t = 1 → final del trail (ancho normal)

            // Determinar la dirección entre base y tip
            Vector3 baseLocal = transform.InverseTransformPoint(points[i].basePos);
            Vector3 tipLocal = transform.InverseTransformPoint(points[i].tipPos);

            // Vector base tip (ancho del trail)
            Vector3 widthDir = tipLocal - baseLocal;

            // Escalo el ancho
            Vector3 scaledWidth = widthDir * t;

            // Reposicionar los vértices ya escalados
            vertices[i * 2] = baseLocal;
            vertices[i * 2 + 1] = baseLocal + scaledWidth;

            colors[i * 2] = new Color(1, 1, 1, alpha);
            colors[i * 2 + 1] = new Color(1, 1, 1, alpha);

            if (i < points.Count - 1)
            {
                int start = i * 6;
                int v = i * 2;
                triangles[start] = v;
                triangles[start + 1] = v + 1;
                triangles[start + 2] = v + 2;
                triangles[start + 3] = v + 1;
                triangles[start + 4] = v + 3;
                triangles[start + 5] = v + 2;
            }
        }

        mesh.Clear();
        mesh.vertices = vertices;
        mesh.colors = colors;
        mesh.triangles = triangles;
        mesh.RecalculateBounds();
    }

    public void StartTrail()
    {
        trailActive = true;
        stoppingTrail = false;
    }

    public void StopTrail()
    {
        if (!stoppingTrail)
        {
            trailActive = false;
            stoppingTrail = true;
            fadeStartTime = Time.time;

            // sincronizar el tiempo de todos los puntos para que se desvanezcan juntos
            for (int i = 0; i < points.Count; i++)
                points[i].timeCreated = fadeStartTime - (pointLifetime - 0.001f);
        }
    }
}
