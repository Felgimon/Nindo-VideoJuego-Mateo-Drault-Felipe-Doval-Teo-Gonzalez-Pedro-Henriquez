using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class Puertas : MonoBehaviour
{
    // Start is called before the first frame update
    private Transform kaito;
    [SerializeField] float distanceRange = 3f;
    private Animator puertaAnimator;
    void Start()
    {
        kaito = GameObject.FindGameObjectWithTag("PlayerBody").transform;
        puertaAnimator = GetComponent<Animator>();
    }

    // Update is called once per frame
    void Update()
    {
        if (Vector3.Distance(transform.position, kaito.position) < distanceRange)
        {
            puertaAnimator.SetBool("isInRange", true);
        } else
        {
            puertaAnimator.SetBool("isInRange", false);
        }
    }
}
