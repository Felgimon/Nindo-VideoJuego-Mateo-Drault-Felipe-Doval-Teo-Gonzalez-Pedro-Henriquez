// Niebla de la cascada: láminas horizontales de ruido posterizado (3 escalones de alfa con cortes duros, como
// manchas de tinta aguada) que salen del pozo y corren hacia la arena. FX/KohanFalls.cs acumula el
// desplazamiento (_Scroll) para que las ráfagas aceleren sin saltos.
// Legibilidad: la niebla se abre alrededor de Kaito y del jefe (_NindoPlayerPos / _NindoBossPos, globales; w = 1
// si hay jefe): nunca tapa a los que pelean.
Shader "Nindo/Mist"
{
    Properties
    {
        _Color ("Color", Color) = (0.725, 0.78, 0.847, 1)
        _AlphaStep ("Alfa por escalón", Range(0, 0.2)) = 0.04
        _Scale ("Tamaño de las manchas (1/m)", Range(0.02, 1)) = 0.16
        _Scroll ("Desplazamiento (xy, m)", Vector) = (0, 0, 0, 0)
        _Source ("Pozo (xz mundo) y radio (z)", Vector) = (0, 0, 14, 0)
        _Seed ("Semilla", Float) = 0
        _Clear ("Radio despejado (m)", Range(0, 6)) = 2.6
    }

    SubShader
    {
        Tags { "RenderType" = "Transparent" "Queue" = "Transparent" "RenderPipeline" = "UniversalPipeline" "IgnoreProjector" = "True" }

        Pass
        {
            Name "Mist"
            Tags { "LightMode" = "UniversalForward" }
            Blend SrcAlpha OneMinusSrcAlpha
            ZWrite Off
            Cull Off

            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fog
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _Color;
                half _AlphaStep;
                float _Scale;
                float4 _Scroll;
                float4 _Source;
                float _Seed;
                float _Clear;
            CBUFFER_END

            float4 _NindoPlayerPos;
            float4 _NindoBossPos;

            struct Attributes { float4 positionOS : POSITION; float2 uv : TEXCOORD0; };
            struct Varyings { float4 positionCS : SV_POSITION; float3 positionWS : TEXCOORD0; float2 uv : TEXCOORD1; float fogFactor : TEXCOORD2; };

            float Hash(float2 p) { return frac(sin(dot(p, float2(12.9898, 78.233))) * 43758.5453); }
            float VNoise(float2 p)
            {
                float2 i = floor(p), f = frac(p);
                f = f * f * (3.0 - 2.0 * f);
                return lerp(lerp(Hash(i), Hash(i + float2(1, 0)), f.x), lerp(Hash(i + float2(0, 1)), Hash(i + float2(1, 1)), f.x), f.y);
            }

            Varyings vert(Attributes input)
            {
                Varyings o;
                o.positionWS = TransformObjectToWorld(input.positionOS.xyz);
                o.positionCS = TransformWorldToHClip(o.positionWS);
                o.uv = input.uv;
                o.fogFactor = ComputeFogFactor(o.positionCS.z);
                return o;
            }

            half4 frag(Varyings input) : SV_Target
            {
                float2 p = input.positionWS.xz;
                float2 q = (p - _Scroll.xy) * _Scale + _Seed;
                float n = VNoise(q) * 0.65 + VNoise(q * 2.3 + 7.1) * 0.35;
                // más densa junto al pozo y en el centro de la lámina; el contorno escalonado sigue esa caída
                float src = 1.0 - smoothstep(_Source.z * 0.35, _Source.z, distance(p, _Source.xy));
                float edge = 1.0 - smoothstep(0.32, 0.5, length(input.uv - 0.5));
                n *= lerp(0.45, 1.15, src) * edge;
                half a = _AlphaStep * (half)(step(0.42, n) + step(0.58, n) + step(0.74, n));
                // claro alrededor de los que pelean
                float clear = smoothstep(_Clear * 0.7, _Clear * 1.35, distance(p, _NindoPlayerPos.xz));
                clear *= lerp(1.0, smoothstep(_Clear, _Clear * 1.9, distance(p, _NindoBossPos.xz)), saturate(_NindoBossPos.w));
                a *= (half)clear;
                Light mainLight = GetMainLight();
                half3 col = _Color.rgb * (SampleSH(half3(0, 1, 0)) + mainLight.color * 0.35h + 0.12h);
                col = MixFog(col, input.fogFactor);
                return half4(col, a);
            }
            ENDHLSL
        }
    }

    FallBack Off
}
