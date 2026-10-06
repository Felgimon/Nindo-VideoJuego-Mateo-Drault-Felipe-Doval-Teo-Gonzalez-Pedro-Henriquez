// Luna de la pelea final (FX/MoonEclipse): un quad lejano que mira a la cámara, en la dirección de la luna de la
// arena (al norte, detrás del dojo). Se ve en las tomas que miran al cielo (presentación, eclipse, final).
//  _Veil: nubes que la tapan (en la presentación "la luna rompe las nubes").
//  _Eclipse: un disco de tinta entra desde _EclipseDir y la cubre; al final queda una corona violeta con hilos
//  de tinta (Kokuyō cierra el puño sobre la luna). _Flash: destello (cada parry del Acto 3 le devuelve la luz).
// Alfa premultiplicado: el disco tapa las estrellas; el halo se suma.
Shader "Nindo/Moon"
{
    Properties
    {
        [HDR] _MoonColor ("Luna", Color) = (1.9, 1.86, 1.72, 1)
        [HDR] _HaloColor ("Halo", Color) = (0.55, 0.7, 1.0, 1)
        [HDR] _CoronaColor ("Corona del eclipse", Color) = (1.2, 0.4, 3.2, 1)
        _Ink ("Disco de tinta", Color) = (0.07, 0.04, 0.1, 1)
        _Radius ("Radio del disco (0..1 del quad)", Range(0.05, 0.6)) = 0.3
        _Eclipse ("Eclipse", Range(0, 1)) = 0
        _EclipseDir ("Desde dónde entra la tinta", Vector) = (-0.8, 0.6, 0, 0)
        _Veil ("Nubes", Range(0, 1)) = 0
        _Flash ("Destello", Range(0, 2)) = 0
        _Alpha ("Visibilidad", Range(0, 1)) = 1
    }

    SubShader
    {
        Tags { "RenderType" = "Transparent" "Queue" = "Transparent-100" "RenderPipeline" = "UniversalPipeline" "IgnoreProjector" = "True" }
        Blend One OneMinusSrcAlpha
        ZWrite Off
        ZTest LEqual
        Cull Off

        Pass
        {
            Name "Moon"
            Tags { "LightMode" = "UniversalForward" }
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _MoonColor, _HaloColor, _CoronaColor, _Ink;
                float4 _EclipseDir;
                float _Radius, _Eclipse, _Veil, _Flash, _Alpha;
            CBUFFER_END

            struct A { float4 pos : POSITION; float2 uv : TEXCOORD0; };
            struct V { float4 pos : SV_POSITION; float2 p : TEXCOORD0; };

            float hash21(float2 p)
            {
                float3 q = frac(float3(p.xyx) * 0.1031);
                q += dot(q, q.yzx + 33.33);
                return frac((q.x + q.y) * q.z);
            }

            float vnoise(float2 p)
            {
                float2 i = floor(p), f = frac(p);
                float2 u = f * f * (3.0 - 2.0 * f);
                return lerp(lerp(hash21(i), hash21(i + float2(1, 0)), u.x), lerp(hash21(i + float2(0, 1)), hash21(i + float2(1, 1)), u.x), u.y);
            }

            float fbm(float2 p)
            {
                return vnoise(p) * 0.55 + vnoise(p * 2.07 + 3.1) * 0.28 + vnoise(p * 4.13 + 7.7) * 0.17;
            }

            V vert(A i)
            {
                V o;
                o.pos = TransformObjectToHClip(i.pos.xyz);
                o.p = i.uv * 2.0 - 1.0;
                return o;
            }

            half4 frag(V i) : SV_Target
            {
                float t = _Time.y;
                float r = _Radius;
                float d = length(i.p);
                float aa = max(fwidth(d), 1e-4);
                float disc = 1.0 - smoothstep(r - aa, r + aa, d);

                // cara de la luna: mares suaves y algo de relieve (sin texturas)
                float2 mp = i.p / r;
                float maria = smoothstep(0.45, 0.75, fbm(mp * 1.6 + 2.3));
                half3 face = _MoonColor.rgb * (1.0 - 0.28 * maria) * (0.92 + 0.08 * (1.0 - dot(mp, mp)));

                // disco de tinta que entra desde un costado (llega al centro con _Eclipse = 1)
                float2 dir = normalize(_EclipseDir.xy + 1e-5);
                float2 c = dir * (1.0 - _Eclipse) * r * 2.3;
                float inkD = length(i.p - c);
                // borde del disco de tinta con dientes de pincel
                float ang = atan2(i.p.y - c.y, i.p.x - c.x);
                float rough = r * (1.0 + 0.035 * (vnoise(float2(ang * 3.0, t * 0.4)) - 0.5));
                float covered = (1.0 - smoothstep(rough - aa, rough + aa, inkD)) * step(0.001, _Eclipse);

                half3 col = lerp(face, _Ink.rgb, covered) * disc;
                float a = disc;

                // halo: se apaga a medida que la tinta tapa la luna
                float lit = 1.0 - _Eclipse * 0.92;
                float halo = exp(-max(d - r, 0.0) * 9.0) * 0.55 + exp(-max(d - r, 0.0) * 3.0) * 0.18;
                col += _HaloColor.rgb * halo * lit * (1.0 - disc);

                // corona del eclipse: anillo violeta con hilos de tinta que se mueven
                float full = smoothstep(0.75, 1.0, _Eclipse);
                float pa = atan2(i.p.y, i.p.x);
                float rays = 0.55 + 0.45 * vnoise(float2(pa * 5.0 + t * 0.15, t * 0.3));
                // el resplandor con rayos solo afuera del disco (adentro dibujaba rayas sobre la tinta)
                float corona = exp(-abs(d - r * 1.02) * 40.0) + exp(-max(d - r, 0.0) * 7.0) * 0.5 * rays * (1.0 - disc);
                col += _CoronaColor.rgb * corona * full * (1.0 - disc * 0.85);

                // nubes que pasan por delante
                float cl = smoothstep(0.42, 0.7, fbm(i.p * 1.4 + float2(t * 0.03, 0.0)));
                col *= 1.0 - _Veil * (0.35 + 0.6 * cl);
                a *= 1.0 - _Veil * 0.5 * cl;

                col *= 1.0 + _Flash * 2.5;
                col += _HaloColor.rgb * _Flash * exp(-max(d - r, 0.0) * 2.0) * (1.0 - disc);
                return half4(col * _Alpha, saturate(a) * _Alpha);
            }
            ENDHLSL
        }
    }
    Fallback Off
}
