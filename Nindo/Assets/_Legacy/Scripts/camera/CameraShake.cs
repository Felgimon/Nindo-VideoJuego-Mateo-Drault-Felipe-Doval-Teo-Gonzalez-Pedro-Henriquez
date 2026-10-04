using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class CameraShake : MonoBehaviour
{
    [SerializeField] public bool startShaking = false;
    [SerializeField] private AnimationCurve curve;
    [SerializeField] private float shakeDuration = 0.5f;

    IEnumerator Shaking()
    {
        Vector3 startPosition  = transform.position;
        float elapsedTime = 0f;

        while (elapsedTime < shakeDuration) //Durante un segundo mueve la camara en diferentes posiciones frame x frame para generar el efecto de shake
        {
            elapsedTime += Time.deltaTime;
            float strength = curve.Evaluate(elapsedTime / shakeDuration);
            transform.position = startPosition + Random.insideUnitSphere * strength;
            yield return null;
        }
        transform.position = startPosition;
    }
    
    void Update()
    {
        if (startShaking)
        {
            startShaking = false;
            StartCoroutine(Shaking());
        }
    }
}
