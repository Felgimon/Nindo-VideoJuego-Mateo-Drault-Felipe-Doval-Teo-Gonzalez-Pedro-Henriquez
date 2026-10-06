// Cuerdas de sombra que atan al abuelo al poste (FX/ShadowRopes). Tubos facetados armados por código:
// uv.x a lo largo de la cuerda (en metros), uv.y alrededor. Cuerda violeta oscura con hebras torcidas que
// brillan y pulsos de luz que corren por ella (se ven desde lejos con el bloom). _Dissolve 0 -> 1 las deshace
// con ruido y un borde encendido, cuando Kokuyō cae: "está libre". El brillo tiene el azul alto y el verde bajo:
// con el tonemapping ACES un violeta "parejo" (1.6, 0.9, 3.2) se lavaba a lila casi blanco.
Shader "Nindo/ShadowRope"
{
    Properties
    {
        [HDR] _Color ("Brillo", Color) = (0.9, 0.25, 2.6, 1)
        _Dark ("Cuerda", Color) = (0.16, 0.09, 0.26, 1)
        [HDR] _EdgeColor ("Borde al deshacerse", Color) = (3.0, 2.4, 4.0, 1)
        _Dissolve ("Disolución", Range(0, 1)) = 0
        _Glow ("Intensidad", Range(0, 2)) = 1
        _Seed ("Semilla", Float) = 0
    }

    SubShader
    {
        Tags { "RenderType" = "TransparentCutout" "Queue" = "AlphaTest" "RenderPipeline" = "UniversalPipeline" "IgnoreProjector" = "True" }
        Cull Back

        Pass
        {
            Name "Rope"
            Tags { "LightMode" = "UniversalForward" }
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fog
            #pragma multi_compile_instancing
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _Color, _Dark, _EdgeColor;
                float _Dissolve, _Glow, _Seed;
            CBUFFER_END

            struct A { float4 pos : POSITION; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; float3 wpos : TEXCOORD1; float fog : TEXCOORD2; UNITY_VERTEX_OUTPUT_STEREO };

            float hash31(float3 p)
            {
                p = frac(p * 0.1031);
                p += dot(p, p.zyx + 31.32);
                return frac((p.x + p.y) * p.z);
            }

            float vnoise(float3 p)
            {
                float3 i = floor(p), f = frac(p);
                float3 u = f * f * (3.0 - 2.0 * f);
                float a = lerp(lerp(hash31(i), hash31(i + float3(1, 0, 0)), u.x), lerp(hash31(i + float3(0, 1, 0)), hash31(i + float3(1, 1, 0)), u.x), u.y);
                float b = lerp(lerp(hash31(i + float3(0, 0, 1)), hash31(i + float3(1, 0, 1)), u.x), lerp(hash31(i + float3(0, 1, 1)), hash31(i + float3(1, 1, 1)), u.x), u.y);
                return lerp(a, b, u.z);
            }

            V vert(A i)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.wpos = TransformObjectToWorld(i.pos.xyz);
                o.pos = TransformWorldToHClip(o.wpos);
                o.uv = i.uv;
                o.fog = ComputeFogFactor(o.pos.z);
                return o;
            }

            half4 frag(V i) : SV_Target
            {
                float t = _Time.y;
                // disolución: manchas de ruido que se comen la cuerda, con un borde encendido
                float n = vnoise(i.wpos * 7.0 + _Seed) * 0.7 + vnoise(i.wpos * 19.0) * 0.3;
                float cut = _Dissolve * 1.15;
                clip(n - cut);
                float edge = (1.0 - smoothstep(cut, cut + 0.07, n)) * step(0.001, _Dissolve);

                // hebras torcidas (dos espirales) y pulsos que corren a lo largo
                float strand = sin(i.uv.x * 26.0 + i.uv.y * 6.2832 * 2.0 + _Seed) * 0.5 + 0.5;
                float vein = smoothstep(0.72, 0.96, strand);
                float pulse = smoothstep(0.82, 1.0, sin(i.uv.x * 3.0 - t * 2.6 + _Seed) * 0.5 + 0.5);
                float breathe = 0.75 + 0.25 * sin(t * 1.7 + _Seed);
                half3 col = lerp(_Dark.rgb, _Color.rgb, saturate(vein * 0.55 + pulse * 0.8) * breathe * _Glow);
                col += _Dark.rgb * 0.4 * _Glow;
                col = lerp(col, _EdgeColor.rgb, edge);
                return half4(MixFog(col, i.fog), 1);
            }
            ENDHLSL
        }
    }
    Fallback Off
}
