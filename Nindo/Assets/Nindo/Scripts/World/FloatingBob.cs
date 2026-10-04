using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Hace que un objeto flote sobre el agua animada: sube y baja con la misma ola que dibuja el
    /// shader "Nindo/Water Lowpoly" (misma fórmula y mismo reloj) y se balancea un poco.
    /// </summary>
    public class FloatingBob : MonoBehaviour
    {
        public float amplitude = 1f;          // = amplitud de las olas del lago (color.r = 1)
        public float rollDegrees = 3.5f;
        Vector3 basePos;
        Quaternion baseRot;
        float waveHeight = 0.26f, waveSpeed = 1f, phase;

        void Start()
        {
            basePos = transform.position;
            baseRot = transform.rotation;
            phase = (basePos.x * 0.37f + basePos.z * 0.61f) % 6.283f;
            var c = Game.Content;
            var mat = c != null ? c.waterAnimatedMaterial : null;
            // mismo criterio que WorldBuilder.SetupWater: sin agua animada el agua es plana
            if (c == null || !c.useAnimatedWater || mat == null || mat.shader == null || !mat.shader.isSupported)
                waveHeight = 0f;
            else
            {
                if (mat.HasProperty("_WaveHeight")) waveHeight = mat.GetFloat("_WaveHeight");
                if (mat.HasProperty("_WaveSpeed")) waveSpeed = mat.GetFloat("_WaveSpeed");
            }
        }

        /// <summary>Misma fórmula que WaveSum() * _WaveHeight del shader y wave_height() de build_world.py.</summary>
        public static float Wave(float x, float z, float t, float height)
        {
            float h = 0.55f * Mathf.Sin((0.958f * x + 0.287f * z) * 0.35f + t * 1.1f)
                    + 0.30f * Mathf.Sin((-0.371f * x + 0.928f * z) * 0.55f + t * 1.5f)
                    + 0.15f * Mathf.Sin((0.659f * x - 0.753f * z) * 0.90f + t * 2.1f);
            return h * height;
        }

        void Update()
        {
            // _Time.y de URP = Time.time (ScriptableRenderer.SetShaderTimeValues), no el tiempo desde que cargó la escena
            float t = Time.time * waveSpeed;
            float y = Wave(basePos.x, basePos.z, t, waveHeight) * amplitude;
            // inclinación según la pendiente de la ola
            float dx = Wave(basePos.x + 0.8f, basePos.z, t, waveHeight) - Wave(basePos.x - 0.8f, basePos.z, t, waveHeight);
            float dz = Wave(basePos.x, basePos.z + 0.8f, t, waveHeight) - Wave(basePos.x, basePos.z - 0.8f, t, waveHeight);
            float k = rollDegrees / Mathf.Max(0.01f, waveHeight);
            var tilt = Quaternion.Euler(dz * k + Mathf.Sin(t * 0.9f + phase) * 0.6f, 0f, -dx * k);
            transform.SetPositionAndRotation(basePos + Vector3.up * y, tilt * baseRot);
        }
    }
}
