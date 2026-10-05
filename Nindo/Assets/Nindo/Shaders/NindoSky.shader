// Cielo nocturno procedural de Nindo: degradé, estrellas que titilan, luna con halo y
// nubes tenues. Sin texturas (no pesa nada) y funciona en URP como skybox.
Shader "Nindo/Night Sky"
{
    Properties
    {
        _ZenithColor ("Zenith", Color) = (0.015, 0.028, 0.08, 1)
        _MidColor ("Middle", Color) = (0.045, 0.08, 0.16, 1)
        _HorizonColor ("Horizon", Color) = (0.13, 0.19, 0.27, 1)
        _GroundColor ("Ground", Color) = (0.04, 0.055, 0.09, 1)
        _MoonColor ("Moon", Color) = (1.0, 0.97, 0.88, 1)
        _MoonDir ("Moon Direction", Vector) = (0.412, 0.743, -0.527, 0)
        _MoonSize ("Moon Size", Range(0.005, 0.15)) = 0.045
        _MoonGlow ("Moon Glow", Range(0, 2)) = 0.6
        _StarDensity ("Star Density", Range(0.9, 0.9999)) = 0.9965
        _StarBrightness ("Star Brightness", Range(0, 5)) = 1.6
        _CloudColor ("Clouds", Color) = (0.1, 0.13, 0.2, 1)
        _CloudAmount ("Cloud Amount", Range(0, 1)) = 0.35
        _Exposure ("Exposure", Range(0, 4)) = 1
    }
    SubShader
    {
        Tags { "Queue"="Background" "RenderType"="Background" "PreviewType"="Skybox" }
        Cull Off ZWrite Off

        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"

            float4 _ZenithColor, _MidColor, _HorizonColor, _GroundColor, _MoonColor, _CloudColor;
            float4 _MoonDir;
            float _MoonSize, _MoonGlow, _StarDensity, _StarBrightness, _CloudAmount, _Exposure;

            struct appdata { float4 vertex : POSITION; };
            struct v2f { float4 pos : SV_POSITION; float3 dir : TEXCOORD0; };

            v2f vert (appdata v)
            {
                v2f o;
                o.pos = UnityObjectToClipPos(v.vertex);
                o.dir = v.vertex.xyz;
                return o;
            }

            float hash13(float3 p)
            {
                p = frac(p * 0.1031);
                p += dot(p, p.zyx + 31.32);
                return frac((p.x + p.y) * p.z);
            }

            float noise2(float2 p)
            {
                float2 i = floor(p), f = frac(p);
                float a = hash13(float3(i, 1.7));
                float b = hash13(float3(i + float2(1, 0), 1.7));
                float c = hash13(float3(i + float2(0, 1), 1.7));
                float d = hash13(float3(i + float2(1, 1), 1.7));
                float2 u = f * f * (3.0 - 2.0 * f);
                return lerp(lerp(a, b, u.x), lerp(c, d, u.x), u.y);
            }

            float fbm(float2 p)
            {
                float v = 0.0, a = 0.5;
                for (int i = 0; i < 4; i++) { v += a * noise2(p); p *= 2.03; a *= 0.5; }
                return v;
            }

            fixed4 frag (v2f i) : SV_Target
            {
                float3 d = normalize(i.dir);
                float h = d.y;

                // degradé del cielo
                float3 col;
                if (h > 0)
                {
                    float t1 = saturate(h * 3.0);
                    float t2 = saturate((h - 0.25) * 1.6);
                    col = lerp(_HorizonColor.rgb, _MidColor.rgb, t1);
                    col = lerp(col, _ZenithColor.rgb, t2);
                }
                else
                {
                    col = lerp(_HorizonColor.rgb, _GroundColor.rgb, saturate(-h * 6.0));
                }

                // estrellas (celdas en 3D sobre la dirección)
                float3 p = d * 260.0;
                float3 cell = floor(p);
                float rnd = hash13(cell);
                if (rnd > _StarDensity && h > 0.02)
                {
                    float3 c = cell + 0.5 + (float3(hash13(cell + 1.3), hash13(cell + 2.7), hash13(cell + 4.1)) - 0.5) * 0.6;
                    float dist = length(p - c);
                    float star = saturate(1.0 - dist * 2.2);
                    float tw = 0.65 + 0.35 * sin(_Time.y * (1.5 + rnd * 4.0) + rnd * 60.0);
                    float horizonFade = saturate(h * 4.0);
                    col += star * star * _StarBrightness * tw * horizonFade * lerp(float3(0.8, 0.88, 1.0), float3(1.0, 0.92, 0.8), frac(rnd * 37.0));
                }

                // nubes tenues que tapan estrellas
                if (h > 0)
                {
                    float2 uv = d.xz / (h + 0.25) * 1.6 + float2(_Time.y * 0.004, _Time.y * 0.002);
                    float cl = smoothstep(0.55 - _CloudAmount * 0.3, 0.95, fbm(uv));
                    cl *= saturate(h * 5.0);
                    col = lerp(col, _CloudColor.rgb, cl * 0.75);
                }

                // luna
                float3 md = normalize(_MoonDir.xyz);
                float mdot = dot(d, md);
                float ang = acos(clamp(mdot, -1, 1));
                float disk = smoothstep(_MoonSize, _MoonSize * 0.92, ang);
                // cráteres suaves
                float3 tangent = normalize(cross(md, float3(0, 1, 0)));
                float3 bitan = cross(md, tangent);
                float2 muv = float2(dot(d - md, tangent), dot(d - md, bitan)) / _MoonSize;
                float craters = fbm(muv * 2.5 + 3.0);
                float3 moon = _MoonColor.rgb * (2.6 - craters * 0.9);
                float glow = pow(saturate(mdot), 900.0) * 1.2 + pow(saturate(mdot), 40.0) * 0.25 + pow(saturate(mdot), 6.0) * 0.06;
                col += _MoonColor.rgb * glow * _MoonGlow;
                col = lerp(col, moon, disk);

                return fixed4(col * _Exposure, 1);
            }
            ENDCG
        }
    }
    Fallback Off
}
