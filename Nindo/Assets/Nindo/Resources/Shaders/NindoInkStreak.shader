// Tajo del remate: una pincelada de tres franjas (tinta negra al medio, dos filos dorados a los costados) que
// sigue el recorrido de Kaito cuando atraviesa al enemigo. Antes estas tres franjas eran el efecto del equipo
// (LinesAttack) parado como una columna vertical y salía en cada dash; ahora va acostado sobre la trayectoria,
// sea cual sea la dirección, y solo en el remate.
// La dibuja FX/FinisherStreak en un quad que mira a la cámara: u = 0 donde arrancó Kaito, 1 donde aparece;
// v = -1..1 de un filo al otro. _Head pinta el trazo de punta a punta (rápido) y _Tail lo borra desde el
// arranque, como una estela. Alfa premultiplicado: la tinta oscurece, el oro brilla (HDR, bloom). Sin texto ni kanji.
Shader "Nindo/InkStreak"
{
    Properties
    {
        _Gold ("Filo", Color) = (1, 0.82, 0.38, 1)
        _Ink ("Tinta", Color) = (0.043, 0.039, 0.051, 1)
        _Head ("Frente del trazo (0..1)", Range(0, 1)) = 1
        _Tail ("Cola borrada (0..1)", Range(0, 1)) = 0
        _Glow ("Intensidad del oro", Float) = 2.4
        _Seed ("Semilla del pincel", Float) = 0
    }

    SubShader
    {
        Tags { "RenderType" = "Transparent" "Queue" = "Transparent+50" "RenderPipeline" = "UniversalPipeline" "IgnoreProjector" = "True" }
        Blend One OneMinusSrcAlpha
        ZWrite Off
        // el tajo cruza al enemigo: tiene que verse por encima de los cuerpos
        ZTest Always
        Cull Off

        Pass
        {
            Name "InkStreak"
            Tags { "LightMode" = "UniversalForward" }
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _Gold, _Ink;
                float _Head, _Tail, _Glow, _Seed;
            CBUFFER_END

            struct A { float4 pos : POSITION; float2 uv : TEXCOORD0; };
            struct V { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; };

            V vert(A i)
            {
                V o;
                o.pos = TransformObjectToHClip(i.pos.xyz);
                o.uv = float2(i.uv.x, i.uv.y * 2 - 1);
                return o;
            }

            float hash(float2 p) { return frac(sin(dot(p, float2(127.1, 311.7))) * 43758.5453); }
            float vnoise(float2 p)
            {
                float2 i = floor(p), f = frac(p), u = f * f * (3 - 2 * f);
                return lerp(lerp(hash(i), hash(i + float2(1, 0)), u.x), lerp(hash(i + float2(0, 1)), hash(i + float2(1, 1)), u.x), u.y);
            }
            float band(float d, float w, float aa) { return 1 - smoothstep(w - aa, w + aa, d); }

            half4 frag(V i) : SV_Target
            {
                float u = i.uv.x, v = abs(i.uv.y);
                float aa = max(fwidth(i.uv.y) * 1.5, 1e-4);

                // tramo vivo [_Tail, _Head]: se afina en la cola y en la punta (pincel que entra y sale)
                float alive = step(_Tail, u) * step(u, _Head);
                // cola larga y fina (de dónde viene), cuerpo lleno hacia la llegada: se lee la dirección
                float taper = smoothstep(_Tail, _Tail + 0.5, u) * (1 - smoothstep(_Head - 0.06, _Head + 0.001, u) * step(_Head, 0.999));
                float w = taper * (0.88 + 0.24 * vnoise(float2(u * 14 + _Seed, 0.5)));   // presión del pincel

                // tres franjas: tinta al medio, dos filos dorados, y un halo de tinta que los separa del fondo
                float core = band(v, 0.3 * w, aa);
                float edge = band(abs(v - 0.56 * w), 0.085 * w, aa) * step(0.02, w);
                float halo = band(v, 0.78 * w, aa);

                // pincel seco: rayas a lo largo (velocidad) en toda la tinta, que se abren hacia la cola
                float hair = vnoise(float2(u * 5 + _Seed * 3, i.uv.y * 16));
                float dry = 0.16 + smoothstep(_Tail + 0.45, _Tail, u) * 0.45;
                core *= 1 - step(hair, dry);
                edge *= 1 - 0.6 * step(hair, dry * 0.8);

                // punta caliente mientras se pinta
                float tip = (1 - step(0.999, _Head)) * band(abs(u - _Head), 0.03, 0.01) * band(v, 0.7, aa);

                float a = alive;
                core *= a; edge *= a; halo *= a; tip *= a;
                float under = saturate(halo - edge) * 0.55 + core * 0.9;
                half3 rgb = _Ink.rgb * under * (1 - edge) + _Gold.rgb * _Glow * (edge + tip);
                return half4(rgb, saturate(under + edge * 0.9 + tip * 0.5));
            }
            ENDHLSL
        }
    }
}
