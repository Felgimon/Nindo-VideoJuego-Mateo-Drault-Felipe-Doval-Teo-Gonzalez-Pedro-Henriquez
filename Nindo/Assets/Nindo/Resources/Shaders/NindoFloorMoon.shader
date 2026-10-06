// La luna en el piso (FX/MoonEclipse): una tira con la forma de la media luna dorada del medallón central del patio,
// apenas encima del oro. La cámara del juego nunca ve el cielo, así que el eclipse se juega acá:
//  - con luna, el oro toma un brillo frío que respira y un halo corto sobre la piedra;
//  - _Eclipse 0 -> 1: la tinta se la come de cuerno a cuerno (uv.x: 0 = este, 1 = oeste) con un frente violeta
//    de pincel; tapada del todo queda solo una corona violeta finita en el borde de afuera;
//  - _Flash: cada parry (y la luna que vuelve) la enciende blanca entera, tinta incluida.
// uv.y: 1 = borde de adentro, 0 = borde de afuera, -1 = fin del halo. Suma luz (Blend One One): nunca oscurece
// el piso ni tapa los avisos ensō, y el violeta tiene el azul alto y el verde bajo para que el ACES no lo lave.
Shader "Nindo/FloorMoon"
{
    Properties
    {
        [HDR] _MoonColor ("Luna", Color) = (0.42, 0.58, 1.0, 1)
        [HDR] _CoronaColor ("Corona del eclipse", Color) = (0.9, 0.25, 2.6, 1)
        _Eclipse ("Eclipse", Range(0, 1)) = 0
        _Flash ("Destello", Range(0, 2)) = 0
        _Alpha ("Visibilidad", Range(0, 1)) = 1
    }

    SubShader
    {
        Tags { "RenderType" = "Transparent" "Queue" = "Transparent-50" "RenderPipeline" = "UniversalPipeline" "IgnoreProjector" = "True" }
        Blend One One
        ZWrite Off
        ZTest LEqual
        Offset -1, -1
        Cull Off

        Pass
        {
            Name "FloorMoon"
            Tags { "LightMode" = "UniversalForward" }
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fog
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _MoonColor, _CoronaColor;
                float _Eclipse, _Flash, _Alpha;
            CBUFFER_END

            struct A { float4 pos : POSITION; float2 uv : TEXCOORD0; };
            struct V { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; float fog : TEXCOORD1; };

            float hash11(float p)
            {
                p = frac(p * 0.1031);
                p *= p + 33.33;
                return frac(p * (p + p));
            }

            float vnoise(float x)
            {
                float i = floor(x), f = frac(x);
                return lerp(hash11(i), hash11(i + 1.0), f * f * (3.0 - 2.0 * f));
            }

            V vert(A i)
            {
                V o;
                o.pos = TransformObjectToHClip(i.pos.xyz);
                o.uv = i.uv;
                o.fog = ComputeFogFactor(o.pos.z);
                return o;
            }

            half4 frag(V i) : SV_Target
            {
                float t = _Time.y;
                float u = i.uv.x, v = i.uv.y;
                float body = step(0.0, v);
                // halo: cae rápido desde el borde de afuera
                float halo = (1.0 - body) * pow(saturate(1.0 + v), 2.2);
                // los cuernos terminan en punta: el brillo también (no corta en seco)
                float tips = smoothstep(0.0, 0.07, u) * smoothstep(1.0, 0.93, u);

                // frente de tinta: recorre de -0.15 a 1.15 con dientes de pincel que se mueven a lo ancho
                float front = lerp(-0.15, 1.15, _Eclipse) + (vnoise(v * 5.0 + t * 0.9) - 0.5) * 0.06;
                float lit = smoothstep(front, front + 0.1, u);
                float band = exp(-abs(u - front - 0.03) * 26.0) * step(0.001, _Eclipse) * step(_Eclipse, 0.995);

                // con luna: respira lento y una veta de luz corre de cuerno a cuerno
                float breathe = 0.85 + 0.15 * sin(t * 1.3);
                float sheen = smoothstep(0.86, 1.0, sin(u * 6.2832 * 1.5 - t * 0.8) * 0.5 + 0.5);
                half3 col = _MoonColor.rgb * (body * (0.28 + 0.32 * sheen) + halo * 0.35) * lit * breathe;

                // tapada: corona finita sobre el borde de afuera (cuerpo cerca de v = 0 y el arranque del halo)
                float full = smoothstep(0.8, 1.0, _Eclipse);
                float rim = body * (1.0 - smoothstep(0.0, 0.3, v)) + halo * 0.6;
                float flicker = 0.7 + 0.3 * vnoise(u * 9.0 + t * 0.6);
                col += _CoronaColor.rgb * (band * (body + halo * 0.7) * 0.8 + rim * full * 0.35 * flicker);

                col += half3(1.0, 1.0, 1.0) * _Flash * (body * 1.1 + halo * 0.5);
                col *= tips * _Alpha;
                // aditivo: la niebla lo apaga hacia negro (no hacia su color, que lo encendería)
                return half4(MixFogColor(col, half3(0, 0, 0), i.fog), 1.0);
            }
            ENDHLSL
        }
    }
    Fallback Off
}
