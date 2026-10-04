using UnityEngine;
using UnityEngine.Rendering;

namespace Nindo
{
    /// <summary>
    /// Materiales para efectos. Usa los asignados en NindoContent; si faltan, los crea en
    /// runtime con los shaders de URP (configurando transparencia por código).
    /// </summary>
    public static class FXMaterials
    {
        static Material additive, alpha, flash, ghost;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void Reset() { additive = alpha = flash = ghost = null; }

        public static Material Additive
        {
            get
            {
                if (additive == null)
                    additive = Game.Content != null && Game.Content.additiveMaterial != null ? Game.Content.additiveMaterial : MakeParticle("Nindo_FX_Additive", true);
                return additive;
            }
        }

        public static Material Alpha
        {
            get
            {
                if (alpha == null)
                    alpha = Game.Content != null && Game.Content.alphaMaterial != null ? Game.Content.alphaMaterial : MakeParticle("Nindo_FX_Alpha", false);
                return alpha;
            }
        }

        public static Material Flash
        {
            get
            {
                if (flash == null)
                {
                    var sh = FindShader("Universal Render Pipeline/Unlit", "Unlit/Color");
                    flash = new Material(sh) { name = "Nindo_HitFlash" };
                    SetColor(flash, new Color(1f, 0.97f, 0.9f, 1f));
                }
                return flash;
            }
        }

        public static Material Ghost
        {
            get
            {
                if (ghost == null)
                    ghost = Game.Content != null && Game.Content.ghostMaterial != null ? Game.Content.ghostMaterial : MakeUnlitTransparent("Nindo_Ghost", new Color(1f, 0.85f, 0.45f, 0.35f), true);
                return ghost;
            }
        }

        public static Shader FindShader(params string[] names)
        {
            foreach (var n in names)
            {
                var s = Shader.Find(n);
                if (s != null && s.isSupported) return s;
            }
            return Shader.Find("Sprites/Default");
        }

        public static void SetColor(Material m, Color c)
        {
            if (m.HasProperty("_BaseColor")) m.SetColor("_BaseColor", c);
            if (m.HasProperty("_Color")) m.SetColor("_Color", c);
        }

        public static Material MakeParticle(string name, bool additiveBlend)
        {
            var sh = FindShader("Universal Render Pipeline/Particles/Unlit", "Particles/Standard Unlit", "Sprites/Default");
            var m = new Material(sh) { name = name };
            ConfigureTransparent(m, additiveBlend);
            m.SetTexture("_BaseMap", SoftDot);
            m.SetTexture("_MainTex", SoftDot);
            return m;
        }

        public static Material MakeUnlitTransparent(string name, Color c, bool additiveBlend)
        {
            var sh = FindShader("Universal Render Pipeline/Unlit", "Unlit/Transparent");
            var m = new Material(sh) { name = name };
            ConfigureTransparent(m, additiveBlend);
            SetColor(m, c);
            return m;
        }

        /// <summary>Equivalente por código a poner "Surface: Transparent" en el inspector de URP.</summary>
        public static void ConfigureTransparent(Material m, bool additiveBlend)
        {
            if (m.HasProperty("_Surface")) m.SetFloat("_Surface", 1f);
            if (m.HasProperty("_Blend")) m.SetFloat("_Blend", additiveBlend ? 2f : 0f);
            m.SetFloat("_SrcBlend", (float)(additiveBlend ? BlendMode.SrcAlpha : BlendMode.SrcAlpha));
            m.SetFloat("_DstBlend", (float)(additiveBlend ? BlendMode.One : BlendMode.OneMinusSrcAlpha));
            if (m.HasProperty("_SrcBlendAlpha")) m.SetFloat("_SrcBlendAlpha", (float)BlendMode.One);
            if (m.HasProperty("_DstBlendAlpha")) m.SetFloat("_DstBlendAlpha", (float)(additiveBlend ? BlendMode.One : BlendMode.OneMinusSrcAlpha));
            m.SetFloat("_ZWrite", 0f);
            if (m.HasProperty("_Cull")) m.SetFloat("_Cull", 0f);
            m.SetOverrideTag("RenderType", "Transparent");
            m.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            if (additiveBlend) m.EnableKeyword("_BLENDMODE_ADD"); else m.DisableKeyword("_BLENDMODE_ADD");
            m.DisableKeyword("_ALPHAPREMULTIPLY_ON");
            m.renderQueue = (int)RenderQueue.Transparent;
            m.SetShaderPassEnabled("ShadowCaster", false);
            m.SetShaderPassEnabled("DepthOnly", false);
        }

        static Texture2D softDot;
        /// <summary>Textura circular suave generada (para partículas sin depender de assets).</summary>
        public static Texture2D SoftDot
        {
            get
            {
                if (softDot == null)
                {
                    const int S = 64;
                    softDot = new Texture2D(S, S, TextureFormat.RGBA32, true) { name = "Nindo_SoftDot", wrapMode = TextureWrapMode.Clamp };
                    var px = new Color32[S * S];
                    for (int y = 0; y < S; y++)
                        for (int x = 0; x < S; x++)
                        {
                            float dx = (x + 0.5f) / S * 2f - 1f, dy = (y + 0.5f) / S * 2f - 1f;
                            float d = Mathf.Sqrt(dx * dx + dy * dy);
                            float a = Mathf.Clamp01(1f - d);
                            a = a * a * (3f - 2f * a);
                            px[y * S + x] = new Color32(255, 255, 255, (byte)(a * 255));
                        }
                    softDot.SetPixels32(px);
                    softDot.Apply(true, true);
                }
                return softDot;
            }
        }
    }
}
